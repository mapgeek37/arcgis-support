from __future__ import division
import os,sys,socket,shutil,logging,logging.config
import datetime

"""Can be removed if logs is loaded from a context where we are certain that arcpy has
already been loaded by the parent class (the class that created an instance of logs) """
try:
    import arcpy
except:
    print('No arcpy package installed or you are using Python 3.x.')

"""
logs.py

Wrapper around the standard Python logger with support for arcpy logger
(used to display messages in the Results window).
"""


class ArcLogger(logging.Logger):

    __version__ = "1.7"

    def __init__(self, name="arcgis_logger", level=logging.INFO, silent=False):
        self.name = name
        self.level = level
        if not silent:
            print("Starting logging tool...")
        super(ArcLogger, self).__init__(name, level)
        sh = logging.StreamHandler()
        self.addHandler(sh)
        pass

    def getTS(self):
        # Gets a timestamp in a default format (day month time)
        startTime = datetime.datetime.now()
        timeStamp = startTime.strftime("%d%b_%H%M")
        return timeStamp

    def setupDiskLog(self, logFolder, description='', timeStamp=None):
        # Configures a file to log to disk. Description can be any user text.
        # Timestamp is a preset timestamp when the log was started.
        # If timestamp was not initialized by the user, set it up now
        if not timeStamp:
            timeStamp=self.getTS()
        # Put the disk logs in a dedicated logs folder
        if not os.path.exists(logFolder):
            # Create a subfolder for the logs to avoid cluttering the main folder
            try:
                os.makedirs(logFolder)
            except:
                print("%s is not a valid folder." % logFolder)
                return False
        self.diskLogName = os.path.join(logFolder,'Log_%s_%s.txt' % (description,timeStamp))
        file_handler = logging.FileHandler(self.diskLogName)
        self.addHandler(file_handler)
        self.info("Configuring disk log: %s" % self.diskLogName)
        return self.diskLogName

    def useExistingLog(self, existingLogFileName):
        if not os.path.exists(existingLogFileName):
            print("%s is not a valid file." % existingLogFileName)
            return False
        else:
            self.diskLogName = existingLogFileName
            file_handler = logging.FileHandler(self.diskLogName)
            self.addHandler(file_handler)
            self.info("Using existing log file %s" % existingLogFileName)

    def disk(self, msg, diskLogName='', silent=False):
        # Writes a message 'msg' to a log file diskLogName
        # if the diskLogName parameter is absent, it will use self.diskLogName
        # First, check whether the log file has been supplied as a parameter.
        if diskLogName == '':
            diskLogName = self.diskLogName
        self.info(msg)

    # Following methods send messages to the arcpy logger (to be viewed
    # in the Results tab of ArcMap) in addition to the native logger.
    def arcMessage(self, msg):
        # Cannot assume that the arcpy module has already been loaded
        import arcpy
        arcpy.AddMessage(msg)
        self.disk(msg, self.diskLogName, True)

    def arcWarn(self, msg):
        import arcpy
        arcpy.AddWarning(msg)
        self.disk(msg, self.diskLogName, True)

    def arcError(self, msg):
        import arcpy
        arcpy.AddError(msg)
        self.disk(msg, self.diskLogName, True)

    def logLevels(self):
        # Print message at different log levels
        self.debug('DEBUG 5')
        self.info('INFO 4')
        self.warning('WARN 3')
        self.error('ERR 2')
        self.critical('CRIT 1')

    def set_level_num(self, level):
        # Sets the debug level to:
        # 5: DEBUG (Detailed information, typically of interest only when diagnosing problems.)
        # 4: INFO (Confirmation that things are working as expected.)
        # 3: WARNING (Possible issue, but we can continue)
        # 2: ERROR (Serious problem, something went wrong)
        # 1: CRITICAL (The entire program must stop now)
        if level == 5:
            self.setLevel(logging.DEBUG)
        if level == 4:
            self.setLevel(logging.INFO)
        if level == 3:
            self.setLevel(logging.WARNING)
        if level == 2:
            self.setLevel(logging.ERROR)
        if level == 1:
            self.setLevel(logging.CRITICAL)

    def p5(self, msg):
        # Log a message msg at level 5 (DEBUG)
        self.debug(msg)
    def p4(self, msg):
        # Log a message msg at level 4 (INFO)
        self.info(msg)
    def p3(self, msg):
        # Log a message msg at level 3 (WARNING)
        self.warning(msg)
    def p2(self, msg):
        # Log a message msg at level 2 (ERROR)
        self.error(msg)
    def p1(self, msg):
        # Log a message msg at level 1 (CRITICAL)
        self.critical(msg)

    def setLoggingLevelInLoop(self, key):
        # key is a keyboard input object returned by msvcrt.getch()
        # q makes loop processing quiet, v makes it verbose
        print("Key input %s" % key)
        if key.decode("latin-1").upper() == 'V':
            # Verbose, show all detailed messages
            logLevel = 5
            self.setLevel(logging.DEBUG)
            print("Display set to verbose")
            return logLevel
        elif key.decode("latin-1").upper() == 'Q':
            # Quiet, set to standard logging level
            print("Display will be set to quiet")
            logLevel = 4
            self.setLevel(logging.INFO)
            return logLevel
        else:
            pass

logging.setLoggerClass(ArcLogger)
logging.basicConfig()
