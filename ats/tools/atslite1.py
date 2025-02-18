import os
import shutil
import subprocess
import sys
from ats.util.generic_utils import execute, clean_old_sandboxes, \
                                     clean_old_ats_log_dirs, \
                                     set_machine_type_based_on_sys_type, \
                                     get_interactive_partition


def main():
    # -----------------------------------------------------------------------------
    # Get the sys_type
    # See if there is a slurm_job_id (which will be the case if the nodes are
    # pre-allocated on chaos
    # -----------------------------------------------------------------------------
    sys_type     = os.getenv("SYS_TYPE")
    lsb_batch_jid = os.getenv("LSB_BATCH_JID")
    slurm_job_id = os.getenv("SLURM_JOB_ID")
    temp_uname   = os.uname()
    host         = temp_uname[1]

    # Look for file.ats on the command line.  If one is not found, we will attempt
    # to create one,
    # but if one is specified, then verify it exists and then use it.
    #
    # Look for exclusive option
    test_ats_found = False
    test_ats_file = ""
    clean_found = False
    exclusive_found = False
    nosub_found = False

    for index, arg in enumerate(sys.argv):
        #print arg
        if (arg.find('=') >= 0):
            (key, val) = arg.split('=',1)
            sys.argv[index] = key + '="' + val + '"'
        elif (arg.find('exclusive') >= 0):
            exclusive_found = True
        elif (arg.find('clean') >= 0):
            clean_found = True
        elif arg.endswith('.ats'):
            test_ats_file = arg
            if not os.path.exists(test_ats_file):
                sys.exit("Bummer! Did not find test file %s" % (test_ats_file))

    # -----------------------------------------------------------------------------
    # Set default numNodes to 4, but allow user to override it with
    # the --numNodes=99 option
    # Also, if numNodes is found, after saving it for the salloc command we can
    # remove it from the argument list, as it will not be needed further.
    # -----------------------------------------------------------------------------
    if 'rznevada' in host:
        numNodes = 2
    elif 'lassen' in host:
        numNodes = 2
    elif 'trinity_knl' in sys_type:
        numNodes = 32
    elif 'blueos_3_ppc64le_ib_p9' in sys_type:
        numNodes = 2
    elif 'blueos' in sys_type:
        numNodes = 1
    else:
        numNodes = 4

    my_bank = "guests"

    for index, arg in enumerate(sys.argv):
        if (arg.find('nosub') >= 0):
            nosub_found = True
            print("INFO: atslite1 %s option will be used " % arg)
            del sys.argv[index]


    for index, arg in enumerate(sys.argv):
        if (arg.find('numNodes') >= 0):
            (key, val) = arg.split('=',1)
            if val.startswith('"') and val.endswith('"'):   # strip off possible quotes from integer
                val = val[1:-1]
            if val.isdigit():
                numNodes = int(val)
            else:
                print("ATS ERROR: '%s' is invalid" % arg)
                sys.exit(-1)
            print("INFO: atslite1 %s option will use %i nodes" % (arg, numNodes))
            del sys.argv[index]
            break

    for index, arg in enumerate(sys.argv):
        if (arg.find('bank') >= 0):
            (key, val) = arg.split('=',1)
            if val.startswith('"') and val.endswith('"'):   # strip off possible quotes
                val = val[1:-1]
            my_bank = val
            print("INFO: atslite1 %s option will use bank %s" % (arg, my_bank))
            del sys.argv[index]

    # -----------------------------------------------------------------------------
    # call ASC routines to set the machine type based on the sys type and get the
    # name of the interactive partition
    # -----------------------------------------------------------------------------
    if "MACHINE_TYPE" not in os.environ:
        set_machine_type_based_on_sys_type()

    interactive_partition = get_interactive_partition()

    for index, arg in enumerate(sys.argv):
        if (arg.find('partition') >= 0):
            (key, val) = arg.split('=',1)
            if val.startswith('"') and val.endswith('"'):   # strip off possible quotes
                val = val[1:-1]
            interactive_partition = val
            print("INFO: atslite1 will use partition %s" % interactive_partition)

    myats = os.path.join(sys.exec_prefix, 'bin', 'ats')
    cmd = myats + " --verbose " + ' '.join(sys.argv[1:])

    create_test_ats_py = os.path.join(os.getcwd(), "create_test_ats.py")

    # If user did not specify a file, then we will default to test.ats, or attempt to create
    # it if it does not exist using a script the user provides in this directory
    if test_ats_file == "":
        test_ats_file = os.path.join(os.getcwd(), "test.ats")
        cmd = cmd + " " + test_ats_file

    if os.path.exists(test_ats_file):
        print("Found %s." % test_ats_file)
    else:
        if os.path.exists(create_test_ats_py):
            print("Found %s." % create_test_ats_py)
            return_code = execute(create_test_ats_py, None, True)
            if (return_code != 0):
                sys.exit(1)
        else:
            sys.exit("Bummer! Did not find %s or %s" % (test_ats_file, create_test_ats_py))


    clean_old_sandboxes()
    clean_old_ats_log_dirs()

    if nosub_found is True:
        print("nosub option -- running ATS directly on login or pre-allocated node on %s" % sys_type)

    elif 'lassen' in host:
        if lsb_batch_jid is None:
            if clean_found is False:
                cmd = 'bsub -q pdebug -nnodes %d -Is -XF -W 120  -core_isolation 2 %s' % (numNodes, cmd)

    elif 'blueos_3_ppc64le_ib_p9' in sys_type:
        if lsb_batch_jid is None:
            if clean_found is False:
                cmd = 'bsub -nnodes %d -Is -XF -W 120 -G %s -core_isolation 2 %s' % (numNodes, my_bank, cmd)

    elif 'blueos_3_ppc64le_ib' in sys_type:
        if lsb_batch_jid is None:
            if clean_found is False:
                myNumProcs = numNodes * 20
                cmd = 'bsub -x -n %d -Is -XF -W 120 -G %s %s' % (myNumProcs, my_bank, cmd)

    elif exclusive_found is True:
        print("ATS Info: Running script on login node -- each test will have a separate srun allocation")
        cmd = "%s --numNodes=%d" % (cmd, numNodes)

    elif slurm_job_id is None:
        cmd = 'salloc -N %d -p %s --exclusive %s' % (numNodes, interactive_partition, cmd)

    print("Executing: %s" % cmd)

    subprocess.run(cmd.split(), text=True)

# -----------------------------------------------------------------------------
#  Startup
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    main()
