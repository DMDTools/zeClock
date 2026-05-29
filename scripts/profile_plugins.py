"""Profile zeClock to identify plugin hotspots."""
import sys
import signal
import cProfile
import pstats
import io

def handler(signum, frame):
    raise KeyboardInterrupt()

signal.signal(signal.SIGALRM, handler)
signal.alarm(15)

sys.argv = ["zeclock", "--backend", "zedmd", "--no-prompt"]

pr = cProfile.Profile()
pr.enable()
try:
    from zeclock.clock import main
    main()
except (KeyboardInterrupt, SystemExit):
    pass
pr.disable()

s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats("tottime")
ps.print_stats("/app/zeclock/", 50)
print(s.getvalue())
