import threading
from eventlet import greenlib
from eventlet.support.greenlet import greenlet

class socket_rwdescriptor:
    #implements(IReadWriteDescriptor)

    def __init__(self, fileno, read, write, error):
        self._fileno = fileno
        self.read = read
        self.write = write
        self.error = error

    def doRead(self):
        if self.read:
            self.read(self)

    def doWrite(self):
        if self.write:
            self.write(self)

    def connectionLost(self, reason):
        if self.error:
            self.error(self, reason)

    def fileno(self):
        return self._fileno

    logstr = "XXXfixme"

    def logPrefix(self):
        return self.logstr


class Hub:
    # wrapper around reactor that runs reactor's main loop in a separate greenlet.
    # whenever you need to wait, i.e. inside a call that must appear
    # blocking, call hub.switch() (then your blocking operation should switch back to you
    # upon completion)

    # unlike other eventlet hubs, which are created per-thread,
    # this one cannot be instantiated more than once, because
    # twisted doesn't allow that

    # 0-not created
    # 1-initialized but not started
    # 2-started
    # 3-restarted
    state = 0

    def __init__(self):
        assert Hub.state==0, ('This hub can only be instantiated once', Hub.state)
        Hub.state = 1
        self.greenlet = None
        self.errcount = 0

    def switch(self):
        if not self.greenlet:
            self.greenlet = greenlib.tracked_greenlet()
            args = ((self.run,),)
        else:
            args = ()
        try:
           greenlet.getcurrent().parent = self.greenlet
        except ValueError, ex:
           pass
        return greenlib.switch(self.greenlet, *args)

    def run(self, installSignalHandlers=True):
        # main loop, executed in a dedicated greenlet
        from twisted.internet import reactor
        assert Hub.state in [1, 3], ('Run function is not reentrant', Hub.state)

        if Hub.state == 1:
            reactor.startRunning(installSignalHandlers=installSignalHandlers)

        if self.errcount > 10:
            import os
            os._exit(1)
        self.errcount += 1
        try:
            self.mainLoop(reactor)
        #except:
        #    sys.stderr.write('\nexception in mainloop\n')
        #    traceback.print_exc()
        #    raise
        finally:
            Hub.state = 3

    def mainLoop(self, reactor):
        Hub.state = 2
        # the same as reactor's mainLoop, but without try/except(all) catcher
        # since this greenlet's parent is the main greenlet, an exception will be
        # delegated there.
        # for example. when exception is raised in a signal handlers, it should go
        # into the main greenlet.
        # (QQQ when there're no references to a greenlet, it should be killed
        #  with GreenletExit. is it possible for this greenlet to be killed under
        #  such circumstances?)
        while reactor.running:
            # Advance simulation time in delayed event
            # processors.
            reactor.runUntilCurrent()
            t2 = reactor.timeout()
            t = reactor.running and t2
            reactor.doIteration(t)       

    def stop(self):
        from twisted.internet import reactor
        reactor.stop()

    def sleep(self, seconds=0):
        from twisted.internet import reactor
        d = reactor.callLater(seconds, greenlib.switch, greenlet.getcurrent())
        self.switch()

    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        #print 'add_descriptor', fileno, read, write, exc
        descriptor = socket_rwdescriptor(fileno, read, write, exc)
        from twisted.internet import reactor
        if read:
            reactor.addReader(descriptor)
        if write:
            reactor.addWriter(descriptor)
        # XXX exc will not work if no read nor write
        return descriptor

    def remove_descriptor(self, descriptor):
        from twisted.internet import reactor
        reactor.removeReader(descriptor)
        reactor.removeWriter(descriptor)

    # required by GreenSocket
    def exc_descriptor(self, _fileno):
        pass # XXX do something sensible here

    # required by greenlet_body
    def cancel_timers(self, greenlet, quiet=False):
        pass # XXX do something sensible here

    def schedule_call(self, seconds, func, *args, **kwargs):
        from twisted.internet import reactor
        return reactor.callLater(seconds, func, *args, **kwargs)


class DaemonicThread(threading.Thread):
    def _set_daemon(self):
        return True

def make_twisted_threadpool_daemonic():
    from twisted.python.threadpool import ThreadPool
    if ThreadPool.threadFactory != DaemonicThread:
        ThreadPool.threadFactory = DaemonicThread

make_twisted_threadpool_daemonic() # otherwise the program would hang after the main greenlet exited