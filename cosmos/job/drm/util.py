import os
import subprocess32 as subprocess
from cosmos.util.signal_handlers import sleep_through_signals


def convert_size_to_kb(size_str):
    if size_str.endswith('G'):
        return float(size_str[:-1]) * 1024 * 1024
    elif size_str.endswith('M'):
        return float(size_str[:-1]) * 1024
    elif size_str.endswith('K'):
        return float(size_str[:-1])
    else:
        return float(size_str) / 1024


def div(n, d):
    if d == 0.:
        return 1
    else:
        return n / d


def exit_process_group():
    """
    Remove a subprocess from its parent's process group.

    By default, subprocesses run within the same process group as the parent
    Python process that spawned them. Signals sent to the process group will be
    sent to the parent and also to to its children. Apparently SGE's qdel sends
    signals not to a process, but to its process group:

    https://community.oracle.com/thread/2335121

    Therefore, an inconveniently-timed SGE warning or other signal can thus be
    caught and handled both by Cosmos and the subprocesses it manages. Since
    Cosmos assumes all responsibility for job control when it starts a Task, if
    interrupted or signaled, we want to handle the event within Python
    exclusively. This method creates a new process group with only one member
    and thus insulates child processes from signals aimed at its parent.

    For more information, see these lecture notes from 1994:

    http://www.cs.ucsb.edu/~almeroth/classes/W99.276/assignment1/signals.html

    In particular:

    "One of the areas least-understood by most UNIX programmers is process-group
     management, a topic that is inseparable from signal-handling."

    "To make certain that no one could write an easily portable application,
     the POSIX committee added yet another signal handling environment which is
     supposed to be a superset of BSD and both System-V environments."

    "You must be careful under POSIX not to use the setpgrp() function --
     usually it exists, but performs the operation of setsid()."
    """
    return os.setsid()


def run_cli_cmd(
    args,
    interval=15,
    logger=None,
    preexec_fn=exit_process_group,
    retries=1,
    timeout=30,
    trust_exit_code=False,
    **kwargs
):
    """
    Run the supplied cmd, optionally retrying some number of times if it fails or times out.

    You can pass through arbitrary arguments to this command. They eventually
    wind up as constructor arguments to subprocess32.Popen().
    """
    result = None
    while retries:
        retries -= 1
        try:
            result = subprocess.run(
                args,
                check=True,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                timeout=timeout,
                universal_newlines=True,
                **kwargs
            )
            if trust_exit_code:
                retries = 0
            elif result.stdout:
                # do we want an "expected_result_regexp" param?
                retries = 0
        except (subprocess.CalledProcessError, subprocess.TimeoutError) as exc:
            result = exc
        finally:
            if logger is not None:
                if isinstance(result, subprocess.TimeoutError):
                    cause = "exceeded %s-sec timeout" % result.timeout
                else:
                    cause = "had exit code %s" % result.returncode
                plan = "will retry in %s sec" % interval if retries else "final attempt"
                logger.error(
                    "Call to %s %s (%s): stdout=%s, stderr=%s",
                    args[0],
                    cause,
                    plan,
                    result.stdout,
                    result.stderr,
                )
            if retries:
                sleep_through_signals(timeout=interval)

    returncode = result.returncode if hasattr(result, "returncode") else "TIMEOUT"
    return result.stdout, result.stderr, returncode
