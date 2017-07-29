from __future__ import division
print("Starting arcpy within arcsupport module...")
import arcpy
import logs
import os,sys,socket,shutil,math
from collections import defaultdict
import codecs
from random import randint

geom = arcpy.Geometry()

"""
Description: 
arcsupport.py library contains three classes with high-level functions not provided
by arcpy (http://desktop.arcgis.com/en/arcmap/10.3/analyze/arcpy/what-is-arcpy-.htm).
1. The ArcTools class provides support functions and workarounds for various
common arcpy programming tasks that are inconvenient or poorly-implemented in the
"out-of-the-box" version of arcpy.
2. The GeomTools class provides some geometry processing tools that are
not available by default in arcpy, or require a Standard / Advanced license.
3. QualityControl class provides tools to check attribute and geometry
quality of feature classes and tables.

Dependencies: 
- logs.py logging class. 
- arcpy version 10.2 or later
- Python 2.7.x (Python 3.x not supported)
"""


# Configure logging tool
import logging
logger = logs.ArcLogger()
logging.basicConfig()


class ArcTools(object):

    def __init__(self, silent=False):
        try:
            self.blankFileGDB = os.path.join(
                os.environ['ProjectRoot'], 'zzzEmpty.gdb')
        except:
            self.blankFileGDB = ""
        self.TS = logger.getTS()
        # Display last time module was re-loaded.
        if not silent:
            arcpy.AddMessage("ArcTools class (updated %s). " % self.TS)
        pass

    def checkFileGDBIntegrity(self, path):
        if os.path.exists(path) or path == 'in_memory':
            logger.p5("GDB folder: OK,", )
            if arcpy.Describe(path).dataType in ['Workspace','Folder','FeatureDataset','FileSystem']:
                logger.p5("%s integrity: OK" % arcpy.Describe(path).dataType)
                return True
            else:
                logger.p3("The folder is not a real GDB or the GDB is corrupted.")
                return False
        else:
            logger.p3("Folder %s does not exist." % path)
            return False

    def newFileGDB(self, path, name):
        if not name.endswith('.gdb'):
            name = name + '.gdb'
        logger.p5("Creating GDB %s in\n %s" % (name, path))
        src = self.blankFileGDB
        dest = os.path.join(path,name)
        if os.path.exists(dest):
            logger.p3("File GDB %s already exists" % dest)
            return False
        if socket.gethostname().upper() == 'FLOPSY':
            # For unknown reasons, create File GDB may fail, and crash the python interpreter too
            # Instead, copy from the empty file GDB.
            if os.path.exists(self.blankFileGDB):
                logger.p5("Copying over the blank fgdb...")
                shutil.copytree(src,dest,ignore=shutil.ignore_patterns('*.lock'))
            else:
                logger.p5("No empty template GDB found!")
                return False
        else:
            arcpy.AddMessage("Creating file GDB: %s" % dest)
            arcpy.CreateFileGDB_management(path,name)

        # Confirm that the fileGDB was created successfully
        if self.checkFileGDBIntegrity(dest):
            arcpy.AddMessage("GDB created OK.")
            return True
        else:
            logger.p2("Problem creating GDB!")
            return False

    def isLocked(self, obj, datatype):
        # Check if we can get a lock on the output object.
        if arcpy.TestSchemaLock(obj):
            logger.p5("The %s is unlocked: can be overwritten, deleted, or modified." % datatype)
            return True
        else:
            logger.p3("The %s is LOCKED" % datatype)
            return False

    def fcAvailable(self, fc):
        # Check whether the fc actually EXISTS.
        if not arcpy.Exists(fc):
            arcpy.AddMessage("Feature class %s does not exist." % os.path.basename(fc))
            return False

        # Read the base path of the feature class. Verify that the base
        # path is a valid workspace
        basePath = os.path.dirname(fc)
        if not self.checkFileGDBIntegrity(basePath):
            return False

        # Set env variables, overwrite output to true.
        self.setEnvVars(basePath,True,'Disabled','Disabled','DEFAULT')
        # Check whether it really is locked
        return self.isLocked(fc, 'feature class')

    def gdbAvailable(self, gdb):
        # First check whether the gdb actually exists
        if not self.checkFileGDBIntegrity(gdb):
            return False
        # Set env variables, overwrite output to true.
        self.setEnvVars(gdb, True, 'Disabled', 'Disabled', 'DEFAULT')
        # Check whether it really is locked
        return self.isLocked(gdb, 'file GDB')

    def backupFC(self, fc):
        # If we can get a lock on fc_BACKUP, go ahead and do fc to fc.
        # Copy fc OVER fc_BACKUP.
        fcName = os.path.basename(fc)
        backupName = fcName+'_BACKUP'
        workGDB = os.path.dirname(fc)
        # Generate the name of the backup file we are going to overwrite
        backup = fc+'_BACKUP'
        # Make sure the source fc actually exists
        if not arcpy.Exists(fc):
            print("Feature class %s does not exist." % fcName)
            return False
        # First, check whether there is already an existing backup
        if arcpy.Exists(backup):
            # Make sure that fc_BACKUP (feature class that is going to be
            # overwritten) is available, i.e. not locked.
            if not self.fcAvailable(backup):
                print("Backup feature class is LOCKED.")
                return False
        # If we get to this point, backup does not already exist
        # or it is available (NOT locked).
        try:
            print("Backing up %s to %s..." % (fcName, backupName))
            arcpy.FeatureClassToFeatureClass_conversion(fc,workGDB,backupName)
        except:
            logger.p2("Unable to backup %s to %s." % (fcName, backupName))
            return False
        pass

    def calcFeatureComplexity(self, fc):
        # Calculates feature complexity using arcpy.da.SearchCursor
        # to retrieve geometries one at a time
        print("Calculating complexity of feature geometries...")
        fCount = 0
        totalCount = self.getCount(fc)
        maxCpx = 0
        minCpx = 0
        multipartCount = 0
        vSum = 0
        with arcpy.da.SearchCursor(fc,['SHAPE@']) as c:
            for row in c:
                v = row[0].pointCount - row[0].partCount
                if row[0].partCount > 1:
                    multipartCount += 1
                vSum += v
                fCount += 1
                sys.stdout.write('\r')
                print "Processing geometry %s of %s (%s%s complete)..." % (
                    fCount,totalCount,round(((fCount/totalCount)*100),1),'%'),
                if v > maxCpx:
                    maxCpx = v
                if minCpx == 0 and v > 0:
                    # initialize the minimum vertex count by setting it to the vertex count of the
                    # first feature having non-null geom, i.e. at least one vertex
                    minCpx = v
                elif v < minCpx and v > 0:
                    minCpx = v
        msg = "\nSummary Statistics:"
        msg += "Total of %s features." % fCount
        msg += "Average feature complexity: %s vertices." % round((vSum / fCount),2)
        msg += "Maximum complexity: %s vertices." % maxCpx
        msg += "Minimum complexity: %s vertices." % minCpx
        msg += "Multipart features: %s found." % multipartCount
        print(msg)
        if multipartCount > 0:
            print("Please run Multipart to Singlepart before continuing!")
        return msg

    def restoreFC(self, fc):
        # Copies FROM a backup TO an original feature class.
        # Get the base name of the feature class
        fcName = os.path.basename(fc)
        workGDB = os.path.dirname(fc)
        # Generate the name of the fc from which to restore
        backup = fc+'_BACKUP'
        # Make sure the backup actually exists
        if not arcpy.Exists(backup):
            logger.p2("A backup of this fc does not exist.")
            return False
        # Make sure that fc (feature class that is going to be restored
        # from backup) is available, i.e. not locked. Or that it does not exist.
        if self.fcAvailable(fc) or not arcpy.Exists(fc):
            #do the fc to fc. FROM backup TO fc
            print("Restoring from %s..." % os.path.basename(backup))
            arcpy.FeatureClassToFeatureClass_conversion(backup,workGDB,fcName)
        else:
            print("Feature class is locked. Can't restore from backup.")
        pass

    def getSmartRow(self, fields, row):
        # returns a "smart" row object as a dict with reasonable names and
        # the row values added.
        rowDict = {}
        for i in range(0,len(row)):
            rowDict[fields[i]] = row[i]
        return rowDict

    def setRowValues(self, c, row, fields, srows):
        """
        c is an arcpy.da update cursor object
        Row is a complete arcpy.da row object
        fields must be the FULL LIST of fields, in the
        same order and with the same size as the row object
        srows is a list of smartRow DICTIONARY objects
        (field name-value pairs). Should look like this:
        [{'field1':'newVal'},{'field2':123}]
        srows may be a subset of the fields variable, or it may be
        complete (one srow object for each field). """
        for srow in srows:
            logger.p5(' %s' % srow)
            fieldName = list(srow.keys())[0]
            findex = fields.index(fieldName)
            row[findex] = srow[fieldName]
        c.updateRow(row)

    def setSmartRow(self, fields, smartRow):
        """
        Takes a list of existing smartRow values (name-value pairs)
        and returns an arcpy.da row object, with the the smartRow value(s)
        inserted into the appropriate location in the 'row' object, using
        the field names in 'fields' as a reference ('fields' must be
        the same size and same order as 'row', in other words fields must have
        been used to create the cursor that generated the row.)
         THE SMART ROW OBJECT DOES NOT NECESSARILY HAVE TO HAVE A 1:1 CORRESPONDENCE
         WITH THE FIELD LIST. All of the expected items in fields must be present.
        """
        rowList = []
        positionList = {}
        for fieldName in smartRow:
            #Get the index of this fieldName in the fields
            findex = fields.index(fieldName)
            value = smartRow[fieldName]
            positionList[findex] = value
        # sort the positionList, and use it to make a row list
        for key in sorted(positionList.keys()):
            rowList.append(positionList[key])
        # cast row list as a tuple for stupid arc cursor
        row = tuple(rowList)
        return row
        pass

    def getFieldNames(self, fc):
        # Gets all the field names for a feature class
        fieldList = []
        for f in arcpy.ListFields(fc):
            fieldList.append(str(f.name))
        return fieldList

    def getShapeGeomToken(self, fieldList):
        # Gets a field list for a feature class with 'SHAPE@' to allow direct
        # insertion of geometry objects
        for i in range(0,len(fieldList)):
            # Replace 'Shape' with the proper 'SHAPE@' token
            if fieldList[i].upper() == 'SHAPE':
                fieldList[i] = 'SHAPE@'
        return fieldList

    def addShapeGeomToken(self, fieldList):
        # Adds a SHAPE@ token to the start of a field list
        # make sure that 'SHAPE' is not already in the field list.
        if not 'SHAPE@' in fieldList:
            fieldList = ['SHAPE@'] + fieldList
        return fieldList

    def addOIDcolumnToken(self, fieldList):
        """
        Adds a OID@ token to the start of a field list. This will allow us
        to insert values directly into an OID column, regardless of the actual name of
        the column (which may be different between feature classes).
        """
        return ['OID@'] + fieldList

    def getCount(self, fc):
        # Get the count of features in a feature class
        r = arcpy.GetCount_management(fc)
        return int(r.getOutput(0))

    def getFieldNamesRequired(self, fc, req):
        # Gets a list of either required fields (req=True)
        # or non-required fields (req = False)
        fieldList = []
        fieldObjList = arcpy.ListFields(fc)
        for f in fieldObjList:
            if f.required == req:
                #Flag for getting required fields (req=True)
                #or non-required fields (req = False)
                fieldList.append(f.name)
        return fieldList

    def deleteFields(self, fc, action, fieldList):
        # Deletes extra fields from a feature class based on
        # action: 'DEL' or 'KEEP'
        # and the list of fields supplied
        # fieldList: 'ALL' or a list of field names
        try:
            fcName = os.path.basename(fc)
        except:
            fcName = fc
        if not self.fcAvailable(fc):
            logger.p2("Cannot delete fields because this feature class is locked.")
            return False
        fieldsToDelete = []
        # Get the list of existing field names
        fields = self.getFieldNames(fc)

        # Remove required fields from potential field deletion list
        reqFields = self.getFieldNamesRequired(fc,True)
        for f in reqFields:
            fields.remove(f)
        # At this point, we have a list of all attributes, that is
        # user-defined fields, and NONE of the required fields.
        if fieldList == 'ALL' and action == 'DEL':
            # simply delete all fields (only the non-required ones should remain)
            fieldsToDelete = fields
        elif fieldList == 'ALL' and action == 'KEEP':
            fieldsToDelete = []
        elif action == 'DEL' and type(fieldList) is list:
            fieldsToDelete = fieldList
        elif action == 'KEEP' and type(fieldList) is list:
            # for all fields to keep
            for fieldToSkip in fieldList:
                # remove field to keep from list of all fields
                # but only if the field to keep is actually in the list of
                # fields for that feature class.
                if fieldToSkip in fields:
                    fields.remove(fieldToSkip)
            fieldsToDelete = fields

        # Check if there are NO fields to delete
        if len(fieldsToDelete) == 0:
            logger.p3("%s: No fields to delete." % fcName)
            return False

        # Remove any field names that do not exist in the feature class
        for f in fieldsToDelete:
            if f not in fields:
                logger.p3("Field %s does not exist." % f)
                fieldsToDelete.remove(f)

        # Now do the field removal
        print("%s: Deleting fields: %s" % (fcName, fieldsToDelete))
        try:
            arcpy.DeleteField_management(fc,fieldsToDelete)
            return True
        except:
            logger.p2("Couldn't delete fields!")
            return False

    def renameField(self, fc, oldName, newName):
        # Likely reasons for this tool to fail:
        # 1. schema lock
        # 2. field is a required field
        # 3. new field name already exists in fields
        # 4. input feature class is a shapefile (not supported by alter field)

        # Check for a shapefile
        if fc.endswith('.shp'):
            logger.p2("Cannot rename fields in shapefiles.")
            return False

        # Check for schema lock
        if not self.fcAvailable(fc):
            logger.p2("Cannot rename fields because this feature class is locked.")
            return False

        # Check for required fields
        reqFields = self.getFieldNamesRequired(fc,True)
        if oldName in reqFields:
            logger.p2("Cannot rename %s because it is a required field." % oldName)
            return False

        # Check if the new name is a duplicate
        fields = self.getFieldNames(fc)
        if newName in fields:
            logger.p2("A field named %s already exists." % newName)
            return False

        # Check if the old name actually exists in the list of fields
        if oldName not in fields:
            logger.p2("Field name %s does not exist." % oldName)
            return False

        # If we passed all of the above tests, let's try to rename:
        try:
            print("Renaming %s to %s..." % (oldName, newName))
            arcpy.AlterField_management(fc, oldName, newName, newName)
            # newName is there twice for field AND alias.
            return True
        except:
            logger.p2("Unable to rename field %s." % oldName)
            return False

    def renameFieldsToMatchAlias(self, fc):
        """
        Modifies FIELD NAMES so that they match the field alias.
        Does not change field aliases.
        """
        for f in arcpy.ListFields(fc):
            if (f.aliasName != f.name):
                self.renameField(fc, f.name, f.aliasName)

    def renameAliasesToMatchFields(self, fc):
        """
        Modifies FIELD ALIASES so that they match the field names.
        Does not change field names.
        """
        for f in arcpy.ListFields(fc):
            if (f.aliasName != f.name):
                f.aliasName = f.name

    def forceFieldType(self, fc, colName, colType):
        """
        Tries to change a field type to the colType.
        :param fc: input feature class
        :param colName: name of the column to change
        :param colType: destination column type
        :return: False if error, True if ok
        """
        if not colName in self.getFieldNames(fc):
            arcpy.AddMessage('Column %s does not exist' % colName)
            return False
        if colType == 'LONG':
            tmpColName = colName + '_long'
            arcpy.AddField_management(fc, tmpColName, colType)
            # Try to calculate the old field into the new one
            calc = "int(!%s!)" % colName
            try:
                arcpy.CalculateField_management(fc, tmpColName, calc, "PYTHON_9.3")
            except:
                arcpy.AddMessage("Some values in column %s can't cast to %s" % (colName, colType))
                return False
        # Delete the old column, rename tmp column to the old name
        self.deleteFields(fc, 'DEL', [colName])
        self.renameField(fc, tmpColName, colName)
        return True

    def getAllItems(self, workspace):
        # Gets all contents of a workspace, including feature classes and tables
        self.setEnvVars(workspace,True,'Disabled','Disabled','DEFAULT')
        fcList = arcpy.ListFeatureClasses('','All')
        tblList = arcpy.ListTables('','All')
        fcList.extend(tblList)
        return fcList

    def deleteMultipleFC(self, workspace, action, fcList):
        # Depending on the action specified, will either DELETE
        # the feature classes in fcList, or it will KEEP all feature
        # classes in fcList and delete the others.

        fcToDelete = []
        # 1. check if workspace exists and is valid
        if not self.checkFileGDBIntegrity(workspace):
            print("Workspace %s does not exist." % workspace)
            return False

        # 2. if action is 'DEL', simply pass the fcList as list to del
        if action == 'DEL' and type(fcList) is list:
            fcToDelete = fcList

        # 3. if action is 'KEEP', get list of fc in workspace
        # remove items in fcList (delete all others)
        elif action == 'KEEP' and type(fcList) is list:
            fcMasterList = self.getAllItems(workspace)
            for fc in fcList:
                # remove this fc from the master list to delete
                if fc in fcMasterList:
                    fcMasterList.remove(fc)
                else:
                    print('Item %s does not exist.' % fc)
            fcToDelete = fcMasterList

        # Keep all feature classes, i.e. do nothing
        elif action == 'KEEP' and fcList == 'ALL':
            fcToDelete = []

        # 4. if fcList is 'ALL', get list of fc in workspace
        # pass this entire list to delete
        elif action == 'DEL' and fcList == 'ALL':
            fcToDelete = self.getAllItems(workspace)

        # Check if the list to delete is now empty.
        if len(fcToDelete) == 0:
            print("Nothing to delete.")
            return False

        # At this point, fc contains ONLY the basename of each
        # feature class, NOT the full path name. We need the full
        # path name to perform Delete_management.
        # Make a full name for each fc including the path!
        fcToDeleteFullPath = []
        for fc in fcToDelete:
            fcToDeleteFullPath.append(os.path.join(workspace,fc))
        fcToDelete = fcToDeleteFullPath
        # 5. Check if each fc exists. If not, remove from list
        # 6. Check if each fc is locked. If locked, remove from list
        # Performing task 6 will also expicitly perform task 5!
        for fc in fcToDelete:
            if not self.fcAvailable(fc):
                fcToDelete.remove(fc)

        # Actually do the deletion now.
        print("The following items are being deleted:")
        for fc in fcToDelete:
            try:
                print('%s' % os.path.basename(fc))
                arcpy.Delete_management(fc)
            except:
                print("Unable to delete %s." % os.path.basename(fc))

    def setEnv(self, workGDB):
        # Sets environment variables based on common defaults.
        # overwrite True, Z and M geometry disabled, default XY tolerance
        self.setEnvVars(workGDB,True,"DISABLED","DISABLED",'DEFAULT')

    def setEnvVars(self, workGDB, overwrite, Z, M, XYtol):
        # Sets environment variables based on parameters specified.
        logger.p5("Setting environment variables...")
        # First, verify that it's a valid gdb.
        # workGDB.endswith('.gdb') and
        if not self.checkFileGDBIntegrity(workGDB):
            logger.p2("No valid file GDB workspace.")
            return False
        # Set the working gdb
        arcpy.env.workspace = workGDB
        # Set overwrite output
        arcpy.env.overwriteOutput = overwrite
        # Set Z and M flags
        arcpy.env.outputZFlag = Z
        arcpy.env.outputMFlag = M
        # Set xy tolerance
        # Compatibility for old-format parameter as a string
        if type(XYtol) is str and XYtol.endswith("Meters"):
            XYtol = float(XYtol.split(' ')[0])

        if XYtol == 'DEFAULT':
            XYtol = "0.001 Meters"
            XYres = "0.0001 Meters"
        else:
            # Set the default resolution to be one order of magnitude smaller than the tolerance
            # This is widely recommended in ESRI docs and elsewhere
            XYres = XYtol / 10
            # Put the value into a string ending " Meters"
            XYtol = "%s Meters" % XYtol
            XYres = "%s Meters" % XYres
        arcpy.env.XYTolerance = XYtol
        arcpy.env.XYResolution = XYres

        logger.p5("Confirming environment settings:")
        logger.p5("Workspace: %s" % arcpy.env['workspace'])
        logger.p5("Overwrite:%s. Z geom:%s. M geom:%s. XY tolerance:%s. XY resolution:%s." % (
            arcpy.env['overwriteOutput'],arcpy.env['outputZflag'],
            arcpy.env['outputMflag'],arcpy.env['XYTolerance'],arcpy.env['XYResolution']))
        pass

    def setEnvProjection(self, sr):
        # Sets the output environment default projection to sr.
        # sr must be a valid spatial reference object.
        try:
            print("Setting output projection to %s" % sr.name)
            arcpy.env.outputCoordinateSystem = sr
            confirmedSR = arcpy.env['outputCoordinateSystem'].name
            print("Confirming: projection set to %s" % confirmedSR)
            return True
        except:
            print("Unable to set output projection.")
            print("The input spatial reference object may be invalid.")
            return False

    def createSRObject(self, srType, obj, verbose=False):
        # Creates spatial reference objects in 3 ways:
        # 3 ways to set spatial reference.
        srTypeList = ['FC','NAME','WKID']
        if srType.upper() not in srTypeList:
            print(("Spatial reference type must be one of %s" % srTypeList))
            return False

        # 1. From a feature class: srType='FC'
        # Check that the fc exists.
        if srType == 'FC':
            if not arcpy.Exists(obj):
                print("Feature class %s does not exist. Cannot read projection." % obj)
                return False
            else:
                try:
                    sr = arcpy.Describe(obj).spatialReference

                except:
                    print("Unable to read projection from %s" % obj)
                    return False

        # 2. By NAME. Read the name, replace any underscores with spaces.
        if srType == 'NAME' and type(obj) is str:
            obj = obj.replace('_',' ')
            try:
                # Try to create a spatial reference object by name
                sr = arcpy.SpatialReference(obj)

            except:
                print("Unable to set projection to %s. Check spelling." % obj)
                return False
        elif srType == 'NAME' and type(obj) is not str:
            print("Second parameter must be a string!")
            return False

        # 3. By WKID. Read the WKID which must be an integer.
        if srType == 'WKID' and type(obj) is int:
            try:
                # Try to create a spatial reference object by WKID (factory code)
                sr = arcpy.SpatialReference(obj)

            except:
                print("%d does not seem to be a valid factory code (WKID/ESPG ID)." % obj)
                print("Check the code and try again.")
                return False
        elif srType == 'WKID' and type(obj) is not int:
            print("Second parameter must be an integer WKID code!")
            return False

        # 4. Confirm spatial reference.
        msg = "\nSpatial reference created."
        msg += "\nName: %s" % sr.name
        msg += "\nFactory Code (WKID): %s" % sr.factoryCode
        if verbose:
            logger.p5(msg)
        return sr

    def getRegion(self, workGDB, boundary, colName, region):
        # Extracts a region from a boundary file where the 'region' name
        # is stored in the column 'colName'
        # First check if the column specified exists in feature class boundary.
        print("\nExtracting boundary for region %s." % region)
        fields = self.getFieldNames(boundary)
        if not colName in fields:
            # column doesn't exist!
            print("Field %s is missing!" % colName)
            return False
        c = arcpy.da.SearchCursor(boundary,[colName])
        found = False
        # search for the region name.
        for row in c:
            if region == str(row[0]):
                print("%s...OK" % region)
                found = True
        del c
        if not found:
            print("ERROR: No feature found for region %s. Cannot continue." % region)
            return False
        # Extract the polygon region to its own, separate in_memory feature class
        region_lyr = 'rg'
        arcpy.MakeFeatureLayer_management(boundary, region_lyr)
        arcpy.SelectLayerByAttribute_management(region_lyr, 'CLEAR_SELECTION')
        sql = " %s = '%s' " % (colName, region)
        arcpy.SelectLayerByAttribute_management(region_lyr, 'NEW_SELECTION',sql)
        if self.getCount(region_lyr) > 1:
            print("ERROR: More than one boundary with region name %s: %d" % (
                region,self.getCount(region_lyr)))
            return False
        else:
            print("Found exactly one feature with region name %s" % region)
            boundary = os.path.join(workGDB,'%s_boundary' % region)
            arcpy.CopyFeatures_management(region_lyr,boundary)
            return boundary

    def validateField(self, fc, colName, valueList):
        # Validates a feature class on TEXT column 'colName' for values 'valueList'
        print("\nValidating feature class %s..." % os.path.basename(fc))
        rowCount = self.getCount(fc)
        print("Validating %s values in column %s..." % (rowCount, colName))
        # Check that colName actually exists.
        if not colName in self.getFieldNames(fc):
            print("Column %s not found!" % colName)
            return ("Column not found",None,None)
        rowCount = self.getCount(fc)
        processedCount = 0
        badRows = 0
        badRowList = []
        badValueList = []
        badValueIndex = {}
        OIDField = arcpy.Describe(fc).OIDFieldName
        with arcpy.da.SearchCursor(fc, [colName,OIDField]) as c:
            for row in c:
                processedCount += 1
                badVal = row[0]
                badRowOID = row[1]
                if not badVal in valueList:
                    badRows += 1
                    badRowList.append(badRowOID)
                    badValueList.append(badVal)
                    if badVal in list(badValueIndex.keys()):
                        badValueIndex[badVal].append(badRowOID)
                    else:
                        badValueIndex[badVal] = [badRowOID]
            sys.stdout.write('\r')
            print("OK rows: %s. Bad rows: %s. (%s%s)" % (
                processedCount - badRows,badRows,round(((processedCount/rowCount)*100),1),'%'), )
        print("\nFinished validating column %s. %s bad rows." % (colName, badRows))
        if badRows > 0:
            print("WARNING: %s invalid rows for column %s." % (badRows, colName))
            return (badRowList,badValueList,badValueIndex)
        else:
            return (None,None,None)

    def notNullOrEmpty(self, fc, colName):
        # Validates a TEXT column 'colName' for the following:
        # - Not a zero-length (empty) string
        # - Not None type (<Null> in arc tables)
        # - Not white space (tabs, spaces, new line characters, etc.)
        # Returns a list of rows violating the above conditions,
        # or a Null list if there are no failed validations.
        # Also Trims leading and trailing whitespace on valid text items in the column
        rowCount = self.getCount(fc)
        print("Validating %s rows for non-null and non-empty strings in column %s..." % (rowCount, colName))
        # Check that colName exists.
        if not colName in self.getFieldNames(fc):
            print("Column %s not found!" % colName)
            return "Column not found"
        processedCount = 0
        badRows = 0
        badRowList = []
        OIDField = arcpy.Describe(fc).OIDFieldName
        with arcpy.da.UpdateCursor(fc, [colName,OIDField]) as c:
            for row in c:
                processedCount += 1
                testVal = row[0]
                badRowOID = row[1]
                if testVal is None:
                    badRows += 1
                    badRowList.append(badRowOID)
                    continue
                elif len(testVal) == 0 or testVal.isspace():
                    # Empty string or all whitespace characters, invalid
                    badRows += 1
                    badRowList.append(badRowOID)
                    continue
                else:
                    # Valid, non-null, non-empty, non-whitespace string
                    # Trim trailing and leading whitespaces
                    row[0] = testVal.strip()
                    c.updateRow(row)
            # Display progress
            sys.stdout.write('\r')
            print("OK rows: %s. Bad rows: %s. (%s%s)" % (
                processedCount - badRows,badRows,round(((processedCount/rowCount)*100),1),'%'), )
        print("\nFinished validating column %s. %s bad rows." % (colName, badRows))
        if badRows > 0:
            print("WARNING: %s rows with Null, empty string, or whitespace in column %s." % (
                badRows, colName))
            return badRowList
        else:
            return None

    def whitespaceToNulls(self, fc, colName):
        # Converts all whitespace values in TEXT column to <Null> (Python None)
        print("\nConverting whitespace to Nulls in column %s..." % colName)
        if not colName in self.getFieldNames(fc):
            print("Column %s not found!" % colName)
            return False
        expression = "wsToNull(!%s!)" % colName
        codeblock = """def wsToNull(colName):
            if colName.strip() == '' or colName.strip() == 'None':
                return None
            else:
                return colName"""
        try:
            # Execute CalculateField
            arcpy.CalculateField_management(fc, colName, expression, "PYTHON_9.3", codeblock)
            print("Complete!")
            return True
        except:
            print("\nProblem calculating field. Check that %s is a NULLABLE TEXT field." % colName)
            return False

    def appendAndCreate(self, fcList, fc):
        # Appends all feature classes in fcList to output fc
        # If fc does not exist, it will be created.
        if not arcpy.Exists(fc):
            # Take one of the items to be appended and copy it into fc
            baseFC = fcList[0]
            logger.p4("Creating output feature class %s" % os.path.basename(fc))
            arcpy.CopyFeatures_management(baseFC,fc)
            # Remove the item that has been copied from the list of feature classes
            fcList.remove(fcList[0])
        # Append all remaining feature classes in the list to fc
        logger.p4("Appending %s items to %s" % (len(fcList), os.path.basename(fc)))
        arcpy.Append_management(fcList,fc,"NO_TEST")

    def valuesToNulls(self, fc, colName, values):
        # Converts all 'values' found in NUMERIC field to <Null> (Python None)
        # colName must be a string and values must be a list
        # e.g. convert all Zeros to Null
        print("Converting values: %s to Nulls in column %s" % (values,colName))
        # Check if the parameters are of the correct type
        if not type(colName) == str:
            # colName must be a string
            logger.p2("2nd parameter must be a string")
            return False
        if not type(values) == list:
            # values must be a list
            logger.p2("3rd parameter must be a list of numeric values")
            return False
        for val in values:
            # every value in values must be numeric
            if not isinstance(val, (int, float, complex)):
                logger.p2("All values must be numbers")
                return False
        if not colName in self.getFieldNames(fc):
            logger.p2("Column %s not found!" % colName)
            return False
        expression = "valsToNull(!%s!,%s)" % (colName,values)
        # return None in the below code block returns a python None type
        # to the python field calculator, and inserts it into colName
        # (colName contains the value at a specific row for that column)
        codeblock = """def valsToNull(colName,values):
            if colName in values:
                return None
            else:
                return colName"""
        try:
            # Execute CalculateField
            arcpy.CalculateField_management(fc, colName, expression, "PYTHON_9.3", codeblock)
            logger.p4("Complete!")
            return True
        except:
            logger.p2("Problem calculating field. Check that %s is a NULLABLE NUMERIC field." % colName)
            return False

    def isTable(self, fc):
        return arcpy.Describe(fc).dataType == 'Table'

    def isFeatureClass(self, fc):
        try:
            data_type = arcpy.Describe(fc).dataType
            if data_type in ['FeatureClass', 'ShapeFile']:
                return True
            return False
        except IOError:
            return False

    def getValidFieldList(self, fc, fieldList):
        # Returns a valid field list suitable for using in an Insert or
        # Update cursor. Or if a field name is bad, returns False.
        if fieldList == 'ALL':
            # Get the list of non-required fields.
            fieldList = self.getFieldNamesRequired(fc, False)
            # Add the shape token field at the beginning of the list
            if not self.isTable(fc):
                fieldList = ['SHAPE@'] + fieldList
        else:
            # Assume the user has already supplied a field list. Make sure that the fields exist.
            for f in fieldList:
                if f not in self.getFieldNames(fc):
                    print("Field %s does not exist in feature class %s!" % (f, os.path.basename(fc)))
                    return False
            # If we passed to here, all the field names are OK.
            # Only add the SHAPE@ if the input is not a table.
            if not self.isTable(fc):
                # Check whether we need to add the shape token. Match all-caps version
                if not 'SHAPE' in (field.upper() for field in fieldList):
                    # Add the shape token field at the beginning of the list
                    fieldList = ['SHAPE@'] + fieldList
                else:
                    # The shape field already exists, convert to proper shape token
                    fieldList = self.getShapeGeomToken(fieldList)
        logger.p5(fieldList)
        return fieldList

    def getInsertCursor(self, fc, fieldList):
        # returns an insert cursor on feature class fc with fields fieldList
        # fieldList can be 'ALL' or a list of attributes.
        # '@SHAPE' will automatically by added to the list of fields (either at the beginning
        # of the field list, or as a replacement of SHAPE if it already exists in the field list)
        # if the nogeom token is False
        if not 'SHAPE@' in fieldList:
            fieldList = self.getValidFieldList(fc, fieldList)
        if not fieldList:
            return False
        # Have a good field list, and we can open an insert cursor
        ic = arcpy.da.InsertCursor(fc, fieldList)
        return ic

    def getUpdateCursor(self, fc, fieldList, nogeom=False):
        # returns an Update cursor on feature class fc with fields fieldList
        # fieldList can be 'ALL' or a list of attributes (not including Shape!)
        # SHAPE@ token will be added to the list of fields.
        fieldList = self.getValidFieldList(fc, fieldList)
        if not fieldList:
            return False
        # Have a good field list, and we can open an insert cursor
        uc = arcpy.da.UpdateCursor(fc, fieldList)
        return uc

    def startEditing(self, workGDB):
        # Start edit session so we can delete and add rows to multiple tables
        arcpy.AddMessage("\rStarting to edit output table..."),
        self.edit = arcpy.da.Editor(workGDB)
        self.edit.startEditing(False, True)
        self.edit.startOperation()

    def stopEditing(self, workGDB):
        arcpy.AddMessage("\rSaving changes so far..."),
        self.edit.stopOperation()
        self.edit.stopEditing(True)

    def saveAndContinue(self, fc, workGDB, fieldList):
        # Saves editing on workspace workGDB, gets insert and update cursors for
        # fc with fieldList, and starts editing again.
        self.stopEditing(workGDB)
        uc = self.getUpdateCursor(fc, fieldList)
        ic = self.getInsertCursor(fc, fieldList)
        self.startEditing(workGDB)
        # return the cursors
        return (ic, uc)

    def newFCFromTemplate(self, newFC, templateFC, geomType, sr):
        # Creates a new feature class using templateFC for attributes with projection sr
        # sr can also be 'SAME' which means same as the templateFC
        # and a geometry type. geomType must be one of: 'POINT','MULTIPOINT','POLYGON','POLYLINE'
        # Break up the newFC into its components
        workGDB = os.path.dirname(newFC)
        fcName = os.path.basename(newFC)
        if not arcpy.Exists(templateFC):
            print("\nTemplate fc does not exist!")
            return False
        geomTypeList = ['POINT','MULTIPOINT','POLYGON','POLYLINE']
        if not geomType in geomTypeList:
            print("\nInvalid geom type: Must be one of %s" % geomTypeList)
            return False
        if sr == 'SAME':
            # Get the projection from the template file
            sr = self.createSRObject('FC', templateFC)
        fc = arcpy.CreateFeatureclass_management(
            workGDB, fcName, geomType, templateFC, 'DISABLED','DISABLED',sr)
        return fc

    def exportTableToCSV(self, fc, outCSV, userFieldList=[],
                         delimiter=",",
                         exportOID=True,
                         nullFormat=None,
                         exportGeom=False,
                         quoteStrings=True):
        #This always exports a table with strings quoted. It will also check to see if any of your strings contain a delimiter character or a newline, and if so it will stop and ask what to do.
        #First, get all the fields. We'll use the arcpy method since it gives all field details.
        arcpy.AddMessage("\nOptions selected: \nFields: %s \nDelimiter: '%s' Export OID: %s Export Geom: %s" % (userFieldList,delimiter, exportOID, exportGeom))
        try:
            f = open(outCSV, 'a+')
            f.close()
        except:
            arcpy.AddMessage("Cannot open output file!\n%s" % outCSV)
            return False

        # Get all fields at first
        fieldList = arcpy.ListFields(fc)
        textFieldsIndex = []
        # Sanitize the field list by removing OID and shape, if requested
        fieldList2 = []
        arcpy.AddMessage("\nFields found in feature class:")
        for field in fieldList:
            arcpy.AddMessage("%s (%s)" % (field.name,field.type))
            if field.type == 'OID':
                if exportOID:
                    fieldList2.append(field)
                else:
                    continue
            elif field.type == 'Geometry':
                if exportGeom:
                    fieldList2.append(field)
                else:
                    continue
            else:
                if len(userFieldList) > 0:
                    # The user has supplied a field list, so we must limit all fields accordingly
                    if field.name in userFieldList:
                        fieldList2.append(field)
                elif len(userFieldList) == 0:
                    # No user fields supplied. Simply append all other fields
                    fieldList2.append(field)
        arcpy.AddMessage("\n")
        # Find the indexes of all text fields.
        index = 0
        for field in fieldList2:
            if field.type == 'String':
                textFieldsIndex.append(index)
            index += 1
        # Write a header, and make a list of field names for the search cursor
        header = ""
        fieldList3 = []
        for field in fieldList2:
            fieldName = field.name
            fieldList3.append(fieldName)
            if quoteStrings:
                header += '"%s"%s' % (fieldName, delimiter)
            else:
                header += '%s%s' % (fieldName, delimiter)
        # We'll have an extra delimiter at the end, so trim the last char
        header = header[:-1]
        arcpy.AddMessage("Writing header: %s" % header)
        f = codecs.open(outCSV, encoding='utf-8', mode='a+')
        f.write(header+"\n")
        f.close()

        arcpy.AddMessage("CSV out: Checking contents of text fields for trouble:")
        arcpy.AddMessage("Fields to export: %s" % fieldList3)
        arcpy.AddMessage("Text Fields: %s" % textFieldsIndex)
        numFields = len(fieldList3)
        rowCount = 0
        totalRows = self.getCount(fc)
        arcpy.AddMessage("Starting export...")
        import io
        f = io.open(outCSV, encoding='utf-8', mode='a+')
        with arcpy.da.SearchCursor(fc, fieldList3) as c:
            for row in c:
                rowCount += 1
                if rowCount > sys.maxsize:
                    return True
                line = ""
                for i in range(numFields):
                    contents = row[i]
                    if i in textFieldsIndex:
                        # This is a text field. Must quote it!
                        if contents is not None:
                            contents = contents.replace(delimiter, "")
                            if quoteStrings:
                                line += '"%s"%s' % (contents, delimiter)
                            else:
                                line += '%s%s' % (contents, delimiter)
                        else:
                            # Should be of type None, which we don't want quoted
                            line += '%s%s' % (contents, delimiter)
                    else:
                        # Not a text field. Write it as-is
                        line += '%s%s' % (contents, delimiter)
                # Done with this row now. Trim the dangling delimiter.
                line = line[:-1]
                f.write(line+'\n')
                if rowCount % 1000 == 0:
                    # Save every once in a while, if you save with every row it is way too slow.
                    f.close()
                    f = codecs.open(outCSV, encoding='utf-8', mode='a+')
                    arcpy.AddMessage("\rExported row %s of %s..." % (rowCount, totalRows)),
        # Close the file when done.
        f.close()
        arcpy.AddMessage("\nAll done. %s rows exported." % rowCount)

    def listUniqueValues(self, fc, col_names, silent=False, colType=None, limit=None):
        """
        Returns a list of unique values in a specified column of a feature class or table

        Args:
            fc (str): full path and name of fc or table
            col_names (str / list): column name to check, or a list of column names
            colType (str): (optional) type of value, e.g. 'int'

        Returns:
            A list of unique values in the column
        """
        # unique_rows = set ()
        unique_rows = []
        rowcount = 0
        if not type(col_names) is list:
            col_names = [col_names]
        # Make a field type lookup
        field_types = {}
        for field in arcpy.ListFields(fc):
            field_types[field.name] = field.type

        if not silent:
            print('Getting a list of unique values in %s...' % col_names)
        with arcpy.da.SearchCursor(fc, col_names) as c:
            for row in c:
                rowcount += 1
                if limit and rowcount > limit:
                    break
                # Iterate over all columns
                row_list = []
                val = None
                for col_name in col_names:
                    i = col_names.index(col_name)
                    # Check column type
                    val = row[i]
                    # Skip type check on null values
                    if val is None:
                        row_list.append(val)
                        continue
                    if field_types.get(col_name) in ['Integer', 'SmallInteger']:
                        val = int(val)
                    elif field_types.get(col_name) in ['Single', 'Double']:
                        val = float(val)
                    elif field_types.get(col_name) == 'String':
                        val = u''+val
                    row_list.append(val)
                if len(col_names) > 1:
                    row_tuple = tuple(row_list)
                    unique_rows.append(row_tuple)
                else:
                    # Skip null rows
                    if val is None:
                        continue
                    unique_rows.append(val)
                if (rowcount % 10000 == 0) and not silent:
                    arcpy.AddMessage("\rGetting unique values for %s: row %s" % (col_names, rowcount)),
        del c
        if not silent:
            print('Converting list of %s items to a unique set...' % len(unique_rows))
        unique_set = set(unique_rows)
        if not silent:
            print('%s unique values in columns %s' % (len(unique_set), col_names))
        valueList = list(unique_set)
        return valueList

    def mem(self, data, nameOverride=None):
        """
        Copies an object 'data' into an in-memory fc named with a random integer to
        avoid collisions. data can be:
        - a list of geometry objects of the same type
        - a layer
        - a full path name to a feature class (.shp or file GDB)
        :param data: see above
        :return: a string with the properly-escaped name of the in_memory object
        """
        arcpy.env.overwriteOutput = True
        ran = randint(1111111, 9999999)
        if nameOverride:
            outFC = os.path.join('in_memory','%s' % nameOverride)
        else:
            if type(data) is str:
                outFC = os.path.join('in_memory','data_%s' % ran)
            else:
                outFC = os.path.join('in_memory','geom_%s' % ran)
        arcpy.CopyFeatures_management(data, outFC)
        return outFC

    def memName(self, prefix, noRandomSeed=False):
        """
        Generates a random in_memory feature class name with prefix
        :param prefix: string alphanumeric starts with letter
        :return: a string with the properly-escaped in_memory name
        """
        ran = randint(1111111, 9999999)
        if noRandomSeed:
            ran = ''
        outFC = os.path.join('in_memory','%s_%s' % (prefix,ran))
        return outFC

    def getGeom(self, fc):
        """
        Gets geometry of any feature class or layer input
        :param fc: see above
        :return: a list of geom object(s)
        """
        geoms = arcpy.CopyFeatures_management(fc, geom)
        return geoms

    def cleanupWorkspace(self, workspace, fcList):
        # Deletes EMPTY feature classes in a specificied workspace (file GDB or folder).
        # fcList can either be a list of feature classes to check (full names)
        # or the keyword 'ALL' in which case all feature classes will be checked.
        #
        #		ALL EMPTY FEATURE CLASSES (0 RECORDS) WILL BE DELETED!
        #		Therefore, be careful how you use this.
        #
        # This is useful in cases where a collection of template feature classes are created
        # in a file GDB, without any advance knowledge about which ones are going to be
        # populated. Some of them may never be used, in which case it's nice to delete
        # the empty ones to cleanup the workspace. Be careful to NOT run this on a file GDB
        # containing template FC's, which are usually empty in any case.
        if fcList == 'ALL':
            # Get a list of feature classes to process
            fcList = self.getAllItems(workspace)
        for fc in fcList:
            if self.getCount(fc) == 0:
                # Feature class is empty, try to delete it.
                try:
                    arcpy.Delete_management(fc)
                    print("Cleaning up %s" % os.path.basename(fc))
                except:
                    print("Unable to delete %s. May be locked (cursor or open in Arcmap)." % os.path.basename(fc))
                    continue


class GeomTools(object):
    """
    This class contains various methods for working with geometry objects.
    Initialize and set default class variables
    """

    def __init__(self, silent=False):
        try:
            self.blankFileGDB = os.path.join(
                os.environ['ProjectRoot'], 'zzzEmpty.gdb')
        except:
            self.blankFileGDB = ""
        self.arctools = ArcTools(silent=True)
        self.TS = logger.getTS()
        """A test string to make sure that the latest version of arcsupport is loaded
        into memory. Reload in the interactive python console (in command line
        or ArcMap), to be sure that the latest version is re-loaded. """
        if not silent:
            arcpy.AddMessage("GeomTools class (update %s). Latest change:" % self.TS)
        self.sr = self.arctools.createSRObject('WKID', 4326)
        self.srAlbers = self.arctools.createSRObject('WKID', 3005)
        pass

    def remove_holes(self, geom):
        """
        Removes holes from an arcpy Polygon geometry object
        :param geom: arcpy (Polygon) geometry object
        :return: (geom with no holes, True) or (original geom, False)
        """
        if not isinstance(geom, arcpy.Polygon):
            return (geom, False)

        # Return only the first (outer-most) ring
        arr = arcpy.Array()
        for part in geom:
            for point in part:
                if point:
                    arr.append(point)
                else:
                    # Return a geometry with only the outer ring
                    return (arcpy.Polygon(arr, geom.spatialReference), True)
        return (geom, False)

    def calcDistanceLL(self, lat1, long1, lat2, long2):
        # Calculates the approximate distance in meters between a pair of lat-long points
        earthRadius = 6371000
        dLat = math.radians(lat2-lat1)
        dLng = math.radians(long2-long1)
        a = math.sin(dLat/2) * math.sin(dLat/2) + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) \
            * math.sin(dLng/2) * math.sin(dLng/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        dist = float(earthRadius * c)
        return dist

    def calcDistanceBetweenPointsLL(self, pt1, pt2):
        # Calculate the geodesic distance in Canada albers equal-area for
        # any pair of points or point geom objects
        # Source points assumed to be in Lat-Long WGS 1984
        srAlbers = self.arctools.createSRObject('WKID', 102001)
        srWGS_1984 = self.arctools.createSRObject('WKID', 4326)
        # Convert geometries to points if necessary
        if isinstance(pt1, arcpy.PointGeometry):
            pt1 = arcpy.Point(pt1.getPart(0).X, pt1.getPart(0).Y)
        if isinstance(pt2, arcpy.PointGeometry):
            pt2 = arcpy.Point(pt2.getPart(0).X, pt2.getPart(0).Y)
        # Construct a line segment
        arr = arcpy.Array()
        arr.add(pt1)
        arr.add(pt2)
        linegeom = arcpy.Polyline(arr, srWGS_1984)
        lineAlbers = linegeom.projectAs(srAlbers)
        return lineAlbers.length

    def isPolylineClosed(self, geom):
        # Tests a polyline geometry object for closure
        if (geom.firstPoint.X == geom.lastPoint.X):
            if (geom.firstPoint.Y == geom.lastPoint.Y):
                return True
            return False
        else:
            return False

    def erasePolygons(self, eraser, target, outFC):
        """
        Erases polygons from a target layer using polygons from an eraser layer.
        Runs one polygon at a time. Result may be a multi-part polygon.
        :param eraser: eraser polygon feature class
        :param target: target polygon feature class (the objects you want to erase)
        :return: none. erased polygons written to outFC.
        """

        arcpy.AddMessage('Preparing to erase polygons...')
        arcpy.env.overwriteOutput = True
        # Make the output feature class, as an exact copy of the input fc, erase will be performed
        # directly on the output, one feature at a time.
        arcpy.CopyFeatures_management(target, outFC)
        # Get the OID field name
        oidFieldName = arcpy.Describe(outFC).OIDFieldName
        # Make feature layers on this in-memory target fc, and the eraser fc
        arcpy.MakeFeatureLayer_management(outFC, 'targets')
        arcpy.MakeFeatureLayer_management(eraser, 'erasers')
        # Get name of the outFC basename, for use later in selecting
        outFCbase = os.path.basename(outFC)
        totCount = self.arctools.getCount(outFC)
        procCount = 0
        with arcpy.da.UpdateCursor('targets', ['OID@','SHAPE@']) as c:
            for row in c:
                oid = row[0]
                geom = row[1]
                # Select only one polygon at a time
                arcpy.SelectLayerByAttribute_management(
                    'targets',"NEW_SELECTION","%s = %s" % (oidFieldName, oid))
                # Select eraser features that intersect this target polygon, should be only a few
                arcpy.SelectLayerByLocation_management(
                    'erasers',"INTERSECT",'targets',"","NEW_SELECTION")
                # Union these two selections
                erasedFC = "in_memory/erased"
                arcpy.Union_analysis(["targets","erasers"], erasedFC, "ALL")
                arcpy.MakeFeatureLayer_management(erasedFC, 'erasedLyr')
                # Select the polygon (should be only one, possibly multipart)
                # that came from target FC originally
                arcpy.SelectLayerByAttribute_management(
                    'erasedLyr',"NEW_SELECTION","FID_%s <> -1" % outFCbase)
                # Get the geometry of this
                geomErased = self.arctools.getGeom('erasedLyr')[0]
                # Update in_memory FC with the new geometry
                c.updateRow((oid, geomErased))
                procCount += 1
                if procCount % 10 == 0:
                    arcpy.AddMessage('Erased %s of %s (last: %s > %s sq. m)' % (procCount, totCount, geom.area, geomErased.area))
        arcpy.AddMessage('Complete. Erased %s polygons.' % procCount)

    def touchesFuzzy(self, geomSelector, geomTarget, fuzzy):
        """
        Selects geometries at a fuzzy distance away from geomSelector.
        Will try to select geometries in geomTarget (0 or more will be returned)
        :param geomSelector: a geometry object
        :param geomTarget: geometry or list of several geometries
        :param fuzzy: fuzzy distance
        :return: a list of selected geometrie(s)
        """
        arcpy.env.overwriteOutput = True
        # Copy to in_memory but don't use random seed, to prevent mem leaks
        geomSelectorMem = self.arctools.mem(geomSelector, 'geomSelectorMem')
        geomTargetMem = self.arctools.mem(geomTarget, 'geomTargetMem')
        selectLyr = os.path.basename(geomSelectorMem) + '_lyr'
        testLyr = os.path.basename(geomTargetMem) + '_lyr'
        arcpy.Delete_management(selectLyr)
        arcpy.Delete_management(testLyr)
        arcpy.MakeFeatureLayer_management(geomSelectorMem, selectLyr)
        arcpy.MakeFeatureLayer_management(geomTargetMem, testLyr)
        arcpy.SelectLayerByLocation_management(testLyr,
            "WITHIN_A_DISTANCE", selectLyr, "%s Meters" % fuzzy, "NEW_SELECTION")
        # We may now have some items selected in testLyr
        selectedGeom = []
        if (self.arctools.getCount(testLyr)) > 0:
            selectedGeom = arcpy.CopyFeatures_management(testLyr, geom)
        arcpy.SelectLayerByAttribute_management(testLyr, "CLEAR_SELECTION")
        del geomSelectorMem
        del geomTargetMem
        return selectedGeom

    def flipLine(self, geom):
        # Flips an entire line geometry (which may have 2 or multiple points)
        sr = geom.spatialReference
        arr = geom.getPart(0)
        arr2 = arcpy.Array()
        for i in reversed(arr):
            arr2.add(i)
        flipped = arcpy.Polyline(arr2, sr)
        return flipped

    def flipLineSegment(self, geom):
        """ Reverses the direction of a line segment. The segment must be defined
        by only two (x,y) coordinates. """
        if geom.pointCount > 2:
            # Not a simple line segment
            return False
        x1 = geom.firstPoint.X
        y1 = geom.firstPoint.Y
        x2 = geom.lastPoint.X
        y2 = geom.lastPoint.Y
        arr = arcpy.Array()
        #Add points to the array in opposite order
        arr.add(arcpy.Point(x2,y2))
        arr.add(arcpy.Point(x1,y1))
        #Get the spatial reference from the existing geom object
        sr = geom.spatialReference
        flipped = arcpy.Polyline(arr, sr)
        return flipped

    def getAzimuth(self, geom):
        """
        Returns the azimuth of a line geometry from first to last point
        :param geom: arcpy Polyline object
        :return:
        """
        # geom must be a arcpy.Polyline geometry object
        x1 = geom.firstPoint.X
        y1 = geom.firstPoint.Y
        x2 = geom.lastPoint.X
        y2 = geom.lastPoint.Y
        # Calculate the AZIMUTH
        deltaX = x2 - x1
        deltaY = y2 - y1
        azm_absolute = math.atan2(deltaX, deltaY)
        return math.degrees(azm_absolute) % 360

    def extendLineAlongAzimuth(self, geom, distance, direction='AZIMUTH'):
        """ Extends a line by (distance) units from its geometry end point.
        By default, it will extend in the same direction as the azimuth
        from the line's start to end. If direction='OPPOSITE', it will
        extend in the opposite direction, from the line's start point.
        Returns a polyline geometry object. """
        azimuth = self.getAzimuth(geom)
        if direction == 'OPPOSITE':
            azimuth = (azimuth+180.0)%360.0
            geom = self.flipLineSegment(geom)
            if not geom:
                return False
        azimuth = math.radians(azimuth)
        deltaX = distance * math.sin(azimuth)
        deltaY = distance * math.cos(azimuth)
        # Now we can use the endpoint of this geom (it may have been flipped)
        # and extend from there
        startX = geom.firstPoint.X
        startY = geom.firstPoint.Y
        """ Calculate the new end coordinates as a delta from the line end point
        If the line has been flipped, the new endpoint will be the former start point, which means
        that the azimuth is pointing in the opposite direction. """
        newEndX = geom.lastPoint.X + deltaX
        newEndY = geom.lastPoint.Y + deltaY
        # Add points to the array
        arr = arcpy.Array()
        arr.add(arcpy.Point(startX,startY))
        arr.add(arcpy.Point(newEndX,newEndY))
        # Get the spatial reference from the existing geom object
        sr = geom.spatialReference
        extended = arcpy.Polyline(arr, sr)
        return extended
        pass

    def makeLineOnAzimuthFromPoint(self, ptGeom, distance, azimuth):
        """
        Makes a line segment of a specific distance on an azimuth from a start point.
        Same projection will be used as the ptGeom object.
        :param point: arcpy PointGeometry
        :param distance: distance in projected units
        :param azimuth: azimuth along which to extend the line
        :return: arcpy.Polyline object for the line segment, and an arcpy.Point
        object for the projected point
        """
        arr = arcpy.Array()
        arr.add(ptGeom.getPart(0))
        azimuth = math.radians(azimuth)
        deltaX = distance * math.sin(azimuth)
        deltaY = distance * math.cos(azimuth)
        endX = ptGeom.getPart(0).X + deltaX
        endY = ptGeom.getPart(0).Y + deltaY
        arr.add(arcpy.Point(endX, endY))
        pline = arcpy.Polyline(arr, ptGeom.spatialReference)
        endPt = arcpy.Point(endX, endY)
        return (pline, endPt)

    def appendToArrayStart(self, arr, points):
        # Appends a list of points to the START of an arcpy.Array
        newArr = arcpy.Array()
        for point in points:
            newArr.add(point)
        for i in range(0, len(arr)):
            newArr.add(arr.getObject(i))
        return newArr

    def intersectLines(self, x1y1x2y2, x3y3x4y4):
        # Calculates an intersection of these lines, if it exists.
        # First test the bounding boxes
        (x1, y1, x2, y2) = x1y1x2y2
        (x3, y3, x4, y4) = x3y3x4y4
        # Equations for first line
        A1 = y2 - y1
        B1 = x1 - x2
        C1 = A1*x1 + B1*y1
        # Equations for second line
        A2 = y4 - y3
        B2 = x3 - x4
        C2 = A2*x3 + B2*y3
        # Intersection calculation
        det = A1*B2 - A2*B1
        if det == 0:
            return None
        else:
            x = (B2*C1 - B1*C2) / det
            y = (A1*C2 - A2*C1) / det

            # Check whether this x,y is actually on the segments
            if min(x1, x2) < x < max(x1, x2) and min(x3, x4) < x < max(x3, x4) \
                and min(y1, y2) < y < max(y1, y2) and min(y3, y4) < y < max(y3, y4):
                return (x, y)
            else:
                return None

    def buildSpatialIndex(self, geom, grid_scale=100.0, density='ALL'):
        # Assume a single-part geometry. Assume that coordinates are always
        # spaced closer together than the grid_scale value.
        # Default grid size is 100.0, which means the coords will be
        # rounded to two digits *before* the decimal, or the nearest
        # 100 m for a metric projection.
        if density not in ['ALL', 'ENDS']:
            return False
        idx = {}
        arr = geom.getPart(0)
        for i in range(0, len(arr)):
            point = arr.getObject(i)
            key = self.spatialKeyFromPoint(point, grid_scale)
            if key not in idx:
                idx[key] = set()
                idx[key].add(i)
            else:
                idx[key].add(i)
        return idx

    def spatialKeyFromPoint(self, point, grid_size=0.01):
        x = point.X
        y = point.Y
        return self.spatialKey(x, y, grid_size=grid_size)

    def spatialKey(self, x, y, grid_size=0.01, invert=False):
        """
        Builds a spatial key with grid scale from a point
        :param point: arcpy Point object
        :param grid_scale: parameter to control the rounding
        :return: a string key suitable for spatial indexing
        """
        round_factor = (-1) * int(math.log10(abs(grid_size)))
        if invert:
            x_key = int(round(x, round_factor) / grid_size)
            y_key = int(round(y, round_factor) / grid_size)
        else:
            x_key = round(x, round_factor)
            y_key = round(y, round_factor)
        key = '%s:%s' % (x_key, y_key)
        return key

    def makeNearbyKeys(self, lat, lon, max_lat_delta=0.02, max_lon_delta=0.03,
                       grid_size=0.01, min_delta=0.013):
        """
        Generates spatial keys near to a coordinate to select nearby objects
        :param lat: test point lat
        :param lon: test point lon
        :param max_lat_delta: max lat offset
        :param max_lon_delta: max lon offset
        :param grid_size: grid size of the spatial index
        :param min_delta: smallest delta
        :return: a set of surrounding spatial index keys
        """
        import itertools
        lat_increments = set()
        lon_increments = set()
        # origpt = arcpy.PointGeometry(arcpy.Point(lon, lat), self.sr)
        # origpt = origpt.projectAs(self.srAlbers)
        for i in [-1, 1]:
            current_lat = lat
            lat_increments.add(current_lat)
            current_lon = lon
            lon_increments.add(current_lon)
            delta = 0.0
            while delta < max_lat_delta:
                current_lat += i * grid_size
                delta = math.fabs(current_lat - lat)
                lat_increments.add(current_lat)
            delta = 0.0
            while delta < max_lon_delta:
                current_lon += i * grid_size
                delta = math.fabs(current_lon - lon)
                lon_increments.add(current_lon)
        pairs = list(itertools.product(lat_increments, lon_increments))
        newkeys = set()
        for (latnew, lonnew) in pairs:
            # Estimate the distance between these points
            delta_lat = math.fabs(latnew - lat)
            delta_lon = math.fabs(lonnew - lon)
            delta_total = math.sqrt(delta_lat * delta_lat + delta_lon * delta_lon)
            if delta_total < min_delta:
                key = self.spatialKey(lonnew, latnew, grid_size)
                newkeys.add(key)
        return newkeys

    def fuzzyCoordinate(self, coord):
        fuzzy = set()
        fuzzy.add(coord)
        x_round = round(coord / 100.0) * 100.0
        if x_round % 1000.0 == 0:
            x_diff = x_round - coord
            x_fuzz = x_round + x_diff
            fuzzy.add(x_fuzz)
        return fuzzy

    def buildSpatialIndexFC(self, fc):
        # Builds an index for an entire feature class using the two-level key of location (4 x 3)
        # and objectId, followed by array point number. Again, all geoms are assumed to be single-part
        import itertools
        idx = {}
        fields = ['OID@', 'SHAPE@']
        count = self.arctools.getCount(fc)
        tenPercentIdx = int(count / 10)
        if tenPercentIdx == 0:
            tenPercentIdx = 1
        percentIdx = list(range(tenPercentIdx, count, tenPercentIdx))
        proc = 0
        arcpy.AddMessage('Building spatial index for %s features...' % count)
        with arcpy.da.SearchCursor(fc, fields) as c:
            for row in c:
                proc += 1
                oid = row[0]
                if proc in percentIdx:
                    arcpy.AddMessage('Adding feature %s (%s of %s)' % (oid, proc, count))
                geom = row[1]
                arr = geom.getPart(0)
                for i in range(0, len(arr)):
                    """ Build the index including a second level for oid.
                    Add a fuzz factor for coordinates that are close to a spatial key boundary (~50 m)
                    Spatial key boundaries are 1000x1000 m, so if the last 3 digits of the whole number
                    portion of the coordinate are in the range 950 - 999, put in +1 key also, or if
                    000 - 050, put in -1 key also.   """
                    pt = arr.getObject(i)
                    x_coords = self.fuzzyCoordinate(pt.X)
                    y_coords = self.fuzzyCoordinate(pt.Y)
                    xy_coords = list(itertools.product(x_coords, y_coords))
                    for (x, y) in xy_coords:
                        key = '%s:%s' % (str(x)[0:5], str(y)[0:4])
                        if key not in idx:
                            idx[key] = {}
                            # idx[key][oid] = set()
                            idx[key][oid] = []
                            idx[key][oid].append(i)
                        elif oid not in idx.get(key):
                            # idx[key][oid] = set()
                            idx[key][oid] = []
                            idx[key][oid].append(i)
                        else:
                            idx[key][oid].append(i)
        return idx


    def extendLinesToIntersect(self, lineFC, intersectFC, maxDistance,
                               direction='AZIMUTH', extendedLineFC=None):
        """ Tries to extend lines to the nearest intersection in a target FC within a range of
        maxDistance. We assume that the lines are oriented in the correct direction and
        will be extended from their current end point, based on the direction parameter.
        """
        # Create a copy of lineFC for extending lines
        if not extendedLineFC:
            # if an output fc name was not provided, simply append '_ext'
            extendedLineFC = lineFC + '_ext'
        extendedLineFCname = os.path.basename(extendedLineFC)
        arcpy.AddMessage("Making copy of %s for extending..." % os.path.basename(lineFC))
        arcpy.CopyFeatures_management(lineFC, extendedLineFC)
        with arcpy.da.UpdateCursor(extendedLineFC, ['SHAPE@']) as c:
            for row in c:
                geom = row[0]
                # Now extend the line
                geom = self.extendLineAlongAzimuth(geom, maxDistance, direction)
                if not geom:
                    continue
                row = (geom,)
                c.updateRow(row)
        # We have now extended the original lines. Try to find intersections.
        extendedLineIntersectFC = extendedLineFC + '_inter'
        arcpy.AddMessage("Intersecting %s with %s..." % (
            extendedLineFCname, os.path.basename(intersectFC)))
        arcpy.Intersect_analysis(
            [extendedLineFC, intersectFC], extendedLineIntersectFC, "ALL", "", "POINT")
        intersections = {}
        extendedLineFIDcol = 'FID_' + extendedLineFCname

        arcpy.AddMessage("Indexing intersections...")
        # Search through the intersections, index by FID in the transects
        fields = ['SHAPE@', extendedLineFIDcol]
        with arcpy.da.SearchCursor(extendedLineIntersectFC, fields) as c:
            for row in c:
                multiPointGeom = row[0]
                transectFID = row[1]
                # Get all of the intersections, could be more than one
                for i in range(0,multiPointGeom.partCount):
                    ptGeom = multiPointGeom.getPart(i)
                    # Add to the dict of intersections
                    if not transectFID in intersections:
                        intersections[transectFID] = []
                    intersections[transectFID].append(ptGeom)

        """ Now done indexing all the intersections. Regardless of the transect direction,
        transects have been extended along a vector FROM start point TO end point. End point
        might be quite some distance away from the original end point, so we will find
        the intersection nearest to the START point.
        """
        arcpy.AddMessage("Extending lines to nearest intersection with %s" %
                         os.path.basename(intersectFC))
        with arcpy.da.UpdateCursor(extendedLineFC, ['SHAPE@', 'OID@']) as c:
            for row in c:
                geom = row[0]
                oid = row[1]
                possibleIntersections = intersections.get(oid)
                if not possibleIntersections:
                    # Didn't find anything
                    continue
                """ possibleIntersections is either None, if the extended transect still does
                not touch the intersect FC, or a list of intersection points (one or more).
                Iterating will allow us to skip those that are None, so that transects that do not
                intersect will not be affected. """
                minDistance = maxDistance + geom.length
                closestIntersection = None
                for inter in possibleIntersections:
                    # Calculate the distance from geom start point to this intersection point
                    firstPointGeom = arcpy.PointGeometry(geom.firstPoint)
                    distance = firstPointGeom.distanceTo(inter)
                    if distance < minDistance:
                        minDistance = distance
                        closestIntersection = inter
                # Done finding the closest intersection
                if not closestIntersection:
                    # Didn't find anything
                    continue
                # Construct the new, fully extended line segment FROM geom.firstPoint TO the intersection
                arr = arcpy.Array()
                startPoint = arcpy.Point(geom.firstPoint.X, geom.firstPoint.Y)
                endPoint = arcpy.Point(closestIntersection.X, closestIntersection.Y)

                if direction == 'AZIMUTH':
                    arr.add(startPoint)
                    arr.add(endPoint)
                elif direction == 'OPPOSITE':
                    arr.add(endPoint)
                    arr.add(startPoint)
                newSegment = arcpy.Polyline(arr)
                newRow = (newSegment, oid)
                c.updateRow(newRow)
        pass

    def polygonToPolyline(self, fc):
        """
        Converts a polygon feature class to closed polylines, one per polygon part.
        No ArcInfo license required. Attributes NOT preserved.
        """
        geom = arcpy.Geometry()
        sr = arcpy.Describe(fc).spatialReference
        pgonList = arcpy.CopyFeatures_management(fc, geom)
        plineList = []
        for p in pgonList:
            for i in range(0,p.partCount):
                pline = arcpy.Polyline(p.getPart(i), sr)
                plineList.append(pline)
        # Create output feature class name
        outfc = fc + "_line"
        arcpy.CopyFeatures_management(plineList, outfc)

    def polygonToPolylineWithData(self, fc, outFCname=None):
        """
        Converts a polygon feature class to closed polylines, one per polygon part.
        No ArcInfo license required. Attributes table is copied. In case of a multi-part
        polygon, the attributes will be assigned to all parts, and one polyline feature
        will be created per part.
        """
        sr = arcpy.Describe(fc).spatialReference
        fcName = os.path.basename(fc)
        # Create a new feature class with the same schema as fc, but as a polyline
        if not outFCname:
            outFCname = fcName + "_line"
        self.arctools.newFCFromTemplate(outFCname, fc, "POLYLINE", sr)
        outFC = outFCname
        # Get non-required fields, and add SHAPE token
        fields = self.arctools.getFieldNamesRequired(fc, False)
        fields = self.arctools.addShapeGeomToken(fields)
        # Use the SAME FIELD LIST for insert cursor, with field for original OID
        fieldsInsert = ['OrigOID'] + fields
        arcpy.AddField_management(outFC, 'OrigOID', "LONG")
        # Add OID field for the input feature class fields
        fields = self.arctools.addOIDcolumnToken(fields)
        cout = arcpy.da.InsertCursor(outFC, fieldsInsert)
        rowCount = 0
        outPlineCount = 0
        with arcpy.da.SearchCursor(fc, fields) as c:
            for row in c:
                rowCount += 1
                srow = self.arctools.getSmartRow(fields, row)
                # Swap the key 'OID@' with 'OrigOID'
                srow['OrigOID'] = srow['OID@']
                del srow['OID@']
                # Extract the polygon geometry and covert to lines
                pgon = srow['SHAPE@']
                for i in range(0, pgon.partCount):
                    pline = arcpy.Polyline(pgon.getPart(i), sr)
                    # Set the SHAPE token to the new Polyline geometry
                    srow['SHAPE@'] = pline
                    """
                    Set a smart row for the insert cursor. We may have multiple parts per input
                     feature, which will be translated into one row *per feature part* in the
                     output. Attributes from the input FC will be duplicated across
                     these rows.
                    """
                    rowInsert = self.arctools.setSmartRow(fieldsInsert, srow)
                    cout.insertRow(rowInsert)
                    outPlineCount += 1

    def polylineExplodeSegments(self, fc):
        """
        Explodes a polyline feature class into individual line segments connecting pairs of points.
        Each polyline in the output will contain only two points. This may produce an output fc with
        a VERY large number of line segments. Be careful with this.
        """
        g = arcpy.Geometry()
        sr = arcpy.Describe(fc).spatialReference

        plineList = arcpy.CopyFeatures_management(fc, g)
        explodedLines = []
        for pline in plineList:
            for j in range(0,pline.partCount):
                # Get the array for this line part
                arr = pline.getPart(j)
                i = 0
                arr.reset()
                previousPoint = None
                while next(arr):
                    p = arr.getObject(i)
                    if previousPoint:
                        lineSegArray = arcpy.Array()
                        lineSegArray.add(previousPoint)
                        lineSegArray.add(p)
                        line = arcpy.Polyline(lineSegArray, sr)
                        explodedLines.append(line)
                        previousPoint = p
                    else:
                        previousPoint = p
                    i += 1
        # Done iterating over all the polylines in this fc.
        # Set output feature class name
        outfc = fc + "_exploded"
        arcpy.CopyFeatures_management(explodedLines, outfc)

    def getGeomFromList(self, geomList, sr):
        # Don't assume anything about geomList except that it is a list of (x,y) coordinate tuples.
        # This function will determine which type of geometry (point, line, polygon)
        # is contained in the coordinate list.
        # Multipart geometries (incl. islands and holes in polygons) are not supported
        # for now. Thus, all inputs must be simplified to single-part prior to extracting the
        # coordinate list that will be sent to this function.
        # Assume sr is a valid spatial reference object.
        #
        # After determining which type of geometry is contained, it will return
        # an arcpy geometry object containing the coordinates, with the projection set to sr.
        # Also returns a text label indicating what type of geometry was found.
        #
        # First, check the length of coordList. If 1, it can only be a point.
        if len(geomList) == 1:
            # We have a point.
            coord = geomList[0]
            (x,y) = coord
            # Add the x,y coords to an arcpy Point object with the spatial reference
            ptGeom = arcpy.PointGeometry(arcpy.Point(x,y), sr)
            return (ptGeom, 'POINT')
        elif len(geomList) > 1:
            # Could be a line or a polygon. Either way, we're going to have to load all the points into
            # an arcpy Array object, so let's start with that step.
            arr = arcpy.Array()
            for coord in geomList:
                (x,y) = coord
                arr.add(arcpy.Point(x,y))
            # Determine what type of geometry we have. If the first coordinate is
            # the same as the last, then it's a closed polygon.
            firstCoord = geomList[0]
            lastCoord = geomList[len(geomList)-1]
            if firstCoord == lastCoord:
                # We have a polygon.
                polyGeom = arcpy.Polygon(arr, sr)
                return (polyGeom, 'POLYGON')
            else:
                # We have a polyline
                lineGeom = arcpy.Polyline(arr, sr)
                return (lineGeom, 'POLYLINE')

    def getGeomType(self, geom):
        # Returns the type of an arcpy geometry object, or various subtypes that may easily be confused.
        # geom must not be a list or any kind of composite object.
        if isinstance(geom, arcpy.Polygon):
            return 'arcpy Polygon'
        if isinstance(geom, arcpy.Polyline):
            return 'arcpy Polyline'
        if isinstance(geom, arcpy.PointGeometry):
            return 'arcpy Point Geometry'
        if isinstance(geom, arcpy.Point):
            return 'arcpy Point'
        if isinstance(geom, arcpy.Array):
            return 'arcpy Array'
        else:
            return 'Not an arcpy type'

    def getGeomAsText(self, geom, xyDelim=',', coordDelim='|',
                      decimals=4, coordOrder='xy'):
        # Returns a text representation of a geometry object. Caveats:
        # geom Must be single-part only. only one geom. Do not supply a list.
        # Default values are supplied above so you only have to call it with the absolute minimum
        # first parameter, or geom.
        # First, let's figure out the type of geometry.
        pts = ''
        geomType = self.getGeomType(geom)
        if geomType == 'Not an arcpy type':
            return "The object supplied does not appear to be a valid arcpy geometry type." \
                   "\nObject type: %s" % type(geom)
        if coordOrder not in ['xy','yx']:
            return "Invalid coordinate order. Must be 'xy' or 'yx'."
        elif geomType == 'arcpy Polygon' or geomType == 'arcpy Polyline':
            # We must assume that the geometry is single-part only. It is always best to work with
            # Single-part geometries in the first place, rather than hacking around them with complex
            # text implementations. Multi-part geom is easy to represent in arcpy objects anyway.
            geom = geom.getPart(0)
            for pt in geom:
                if coordOrder=='xy':
                    pts = "%s%s%s%s%s" % (pts, round(pt.X,decimals), xyDelim,
                                          round(pt.Y, decimals), coordDelim)
                elif coordOrder=='yx':
                    pts = "%s%s%s%s%s" % (pts, round(pt.Y,decimals), xyDelim,
                                          round(pt.X, decimals), coordDelim)
            # Done concatenating all the coordinate pairs.
            return pts

    # Get Distance between two points p1 and p2 in Cartesian coordinates.
    def dist(self, p1,p2):
        x1=p1.X
        x2=p2.X
        y1=p1.Y
        y2=p2.Y
        dist = math.sqrt(math.pow((x2-x1),2)+math.pow((y2-y1),2))
        return dist

    # Get the midpoint of two points, returned as an arcpy Point object
    def midpoint(self, p1, p2):
        fraction = 0.5
        return self.midpointFractional(p1, p2, fraction)

    def midpointFractional(self, p1, p2, fraction):
        # Returns a point on the line between p1 and p2 at a fraction of the distance between
        # those points. e.g. if fraction = 0.1, the point will be located at 10% along
        # the line from p1 to p2
        x1 = p1.X
        y1 = p1.Y
        x2 = p2.X
        y2 = p2.Y
        deltaX = x2 - x1
        deltaY = y2 - y1
        (x,y) = ((x1 + deltaX * fraction), (y1 + deltaY * fraction))
        return arcpy.Point(x,y)

    def splitRectangle(self, rectangle, sr):
        # Takes a rectangle object in the object r consisting of
        # one rectangle polygon geometry (not a feature class!)
        # and returns the rectangle cut in half, splitting the long axis evenly,
        # returned as a pair of geometries with projection sr, in a list.
        arr = rectangle.getPart(0)
        # Extract the points from the polygon array in order, to a pts dictionary
        pts = {}
        ptCount = 0
        for pt in arr:
            ptCount += 1
            pts[ptCount] = pt
        # Build edges of a polygon (for a rectangle, but could be applied to any shape)
        edges = {}
        for i in range(1,len(pts)+1):
            if i > 1:
                edges[i-1] = {}
                edges[i-1]['from'] = pts[i-1]
                edges[i-1]['to'] = pts[i]
                edges[i-1]['length'] = 0
        # Set the length of polygon edges
        for i in range(1,5):
            edges[i]['length'] = self.dist(edges[i]['from'],edges[i]['to'])
        # Get the two longest edge lengths (the two longest should be the
        # same length, but ya never know)
        edgeLengths = []
        for i in range(1,5):
            edgeLengths.append(edges[i]['length'])
        longEdges = sorted(edgeLengths)[-2:]
        # Assign a boolean for whether each edge is a long edge
        for i in range(1,5):
            if edges[i]['length'] in longEdges:
                edges[i]['longEdge'] = True
            else:
                edges[i]['longEdge'] = False
        # Get the midpoints of each edge
        for i in range(1,5):
            edges[i]['midpoint'] = self.midpoint(edges[i]['from'],edges[i]['to'])
        # If needed, renumber the edges so that the rectangle starts
        # with the first long edge
        edg = {}
        # Sort edges so that the first edge is a long edge
        if not edges[1]['longEdge']:
            edg[1] = edges[2]
            edg[2] = edges[3]
            edg[3] = edges[4]
            edg[4] = edges[1]
        else:
            # use the edges as-is
            edg = edges
        # create a new points dictionary.
        pts = {}
        pts[1] = edg[1]['from']
        pts[2] = edg[2]['from']
        pts[3] = edg[3]['from']
        pts[4] = edg[4]['from']
        pts[6] = edg[1]['midpoint']
        pts[7] = edg[3]['midpoint']
        # Create the first rectangle
        r1 = arcpy.Array()
        for i in [1,6,7,4,1]:
            r1.add(pts[i])
        r1pgon = arcpy.Polygon(r1,sr)
        # Create the second rectangle
        r2 = arcpy.Array()
        for i in [6,2,3,7,6]:
            r2.add(pts[i])
        r2pgon = arcpy.Polygon(r2,sr)
        return [r1pgon, r2pgon]

    def polygonReduction(self, workGDB, fc, reductionRatio, basePts, sr):
        # Takes an input polygon as a feature class 'fc' containing only
        # one polygon. Reduces the length of the polygon until its
        # length (longest axis) is no more than 'reductionRatio' times
        # its width (shortest axis). Only areas of the original polygon
        # containing points in 'basePts' will be kept. Finally returns
        # a feature class containing a single polygon with projection 'sr'
        workGDB = 'in_memory'
        self.arctools.setEnv(workGDB)
        # 1. Get the minimum bounding rectangle
        boundRect = os.path.join(workGDB,"boundRect")
        g = arcpy.Geometry()
        arcpy.MinimumBoundingGeometry_management(fc,boundRect,"RECTANGLE_BY_WIDTH","NONE","","MBG_FIELDS")
        # 2. Read the rectangle's width and length
        logger.p5("Bounding rectangle for this feature: %s " % boundRect)
        length = 1
        width = 1
        with arcpy.da.SearchCursor(boundRect,['MBG_Width','MBG_Length']) as c:
            for row in c:
                logger.p5("Current row: %s" % str(row))
                width = row[0]
                length = row[1]
        # 3. Test the width to length ratio
        ratio = length / width
        logger.p5("Ratio for this feature: %s" % ratio)
        if ratio < reductionRatio:
            # This polygon is not too long. Exit.
            return fc
        else:
            # The polygon is still too long.
            # 4. Get the rectangle geometry (as a list of geometry objects).
            rect = arcpy.CopyFeatures_management(boundRect,g)
            # 5. Send the first rectangle geometry to the rectangle splitter
            rects = self.splitRectangle(rect[0],sr)
            # 6. Split the original fc using the two new rectangles.
            i = 0
            for rect in rects:
                i += 1; arcpy.Clip_analysis(fc,rect,"in_memory/fc%s" % i)
            # 7. Merge the two clipped polygons to one feature class.
            arcpy.Merge_management(["in_memory/fc1","in_memory/fc2"],"in_memory/fcCutInHalf")
            arcpy.RepairGeometry_management("in_memory/fcCutInHalf")
            # 8. Select by location. select the polygon that contains a base point.
            arcpy.MakeFeatureLayer_management("in_memory/fcCutInHalf","fcCutInHalf")
            arcpy.SelectLayerByLocation_management("fcCutInHalf","CONTAINS",basePts)
            # 9. Invert Selection
            arcpy.SelectLayerByAttribute_management("fcCutInHalf","SWITCH_SELECTION")
            # 10. Delete the currently selected feature (the one that does not contain
            # an original point in the basePts feature class)
            arcpy.DeleteFeatures_management("fcCutInHalf")
            fcCut = os.path.join(workGDB,'fcCut')
            arcpy.CopyFeatures_management("fcCutInHalf",fcCut)
            # 11. Call this function again recursively.
            return self.polygonReduction(workGDB,fcCut,reductionRatio,basePts,sr)


class QualityControl(object):

    """
    Performs quality control to flag potential data quality issues.
    """

    def __init__(self, silent=False):
        self.arctools = ArcTools(silent=True)
        self.TS = logger.getTS()
        """A test string to make sure that the latest version of arcsupport is loaded
        into memory. Reload in the interactive python console (in command line
        or ArcMap), to be sure that the latest version is re-loaded. """
        if not silent:
            logger.info("QualityControl class (updated %s). " % self.TS)
        pass

    def field_name_check(self, source, field_names=list()):
        """
        Check field names in data source
        :param source: a data source. If not already in a ESRI-supported format,
        add list of field names to check in second param
        :param field_names: optional list of field names to validate
        :return: list of invalid field names
        """
        import re
        invalid = []
        if not field_names:
            # Use field names defined in the source.
            field_names = self.arctools.getFieldNames(source)
        allowed_patt = '^[a-z][_a-z0-9]*$'
        for field in field_names:
            m = re.match(allowed_patt, field, re.IGNORECASE)
            if m:
                logger.info('Field name %s ok.' % field)
            else:
                logger.warn('Field name %s not valid for ArcGIS' % field)
                invalid.append(field)
        if invalid:
            logger.info('For a list of field name rules, see: '
                        '\nhttp://support.esri.com/technical-article/000005588 ')
        return invalid

    def field_type_check(self, fc):
        """
        Validate field types against the data actually contained in each field
        Look for:
        - numeric data in text field
        - integer data in a double field (all rounded to integer)
        Log warnings that we found.
        :return:
        """
        for field in arcpy.ListFields(fc):
            # in ['Integer', 'SmallInteger']
            if field.type in ['Single', 'Double']:
                vals = self.arctools.listUniqueValues(fc, field.name, silent=True)
                has_decimal = False
                for val in vals:
                    if val % 1 != 0.0:
                        has_decimal = True
                if not has_decimal:
                    logger.warn('Field %s (type %s) contains all integers' % (field.name, field.type))

            if field.type == 'String':
                vals = self.arctools.listUniqueValues(fc, field.name, silent=True)
                has_non_numeric = False
                for val in vals:
                    try:
                        numeric = float(val.strip())
                    except ValueError:
                        has_non_numeric = True
                if not has_non_numeric:
                    logger.warn('Field %s (type %s) contains all numbers' % (field.name, field.type))

    def table_completeness(self, fc):
        """
        Check percent of null / blank in each field
        :return:
        """
        from collections import defaultdict
        fields = self.arctools.getFieldNames(fc)
        null_counts = defaultdict(int)
        row_count = self.arctools.getCount(fc)
        logger.info('Checking table completeness on %s' % fc)
        with arcpy.da.SearchCursor(fc, fields) as c:
            for row in c:
                srow = self.arctools.getSmartRow(fields, row)
                for field in fields:
                    val = srow.get(field)
                    # count nulls, empty or blank strings
                    if self.null_blank_check(val):
                        null_counts[field] += 1
        # Print a summary
        if not null_counts:
            logger.info('No null or blank records found.')
            return
        for (field, nulls) in null_counts.items():
            pct_null = (nulls / row_count) * 100.0
            logger.info('Field %s contains %s%s null or blank records.' % (
                field, pct_null, '%'))

    def null_blank_check(self, val):
        """
        Returns true if val is None or a blank / empty string
        :param val:
        :return:
        """
        if val is None:
            return True
        elif isinstance(val, basestring):
            if len(val.strip()) == 0:
                return True
        return False

    def spatial_ref_check(self, filepath):
        """
        Checks for inconsistent spatial reference or data sources
        with no SR in a workspace
        :return:
        """
        if not os.path.exists(filepath):
            logger.warn('%s is not a valid workspace' % filepath)
            logger.warn('Use a folder or geodatabase path.')
            return False
        try:
            desc = arcpy.Describe(filepath)
            if desc.dataType in ['Workspace', 'Folder']:
                # List all items
                sr_list = defaultdict(list)
                arcpy.env.workspace = filepath
                datasets = arcpy.ListFeatureClasses()
                if len(datasets) == 0:
                    logger.info('No datasets in %s' % filepath)
                    return
                for dataset in datasets:
                    fc = os.path.join(filepath, dataset)
                    sr = arcpy.Describe(fc).spatialReference
                    sr_list[(sr.name, sr.factoryCode)].append(dataset)

                # Print spatial references we found, with warnings
                if len(sr_list) > 1:
                    logger.warn('Warning: more than one spatial reference found in this workspace.')
                logger.info('Most common spatial references:')
                for (sr_name, wkid) in sorted(
                        sr_list, key=lambda x: len(sr_list[x]),
                        reverse=True):  # .items():
                    datasets = sr_list.get((sr_name, wkid))
                    logger.info('%s (WKID %s) %s items: %s' % (
                        sr_name, wkid, len(datasets), ', '.join(datasets)))
                    if sr_name == 'Unknown':
                        logger.warn('Datasets with NO PROJECTION: %s' % ', '.join(datasets))
            else:
                logger.info('Unsupported workspace type: %s' % desc.dataType)
        except IOError:
            logger.warn('Cannot open workspace %s' % filepath)

    def repair_geom_zm(self, fc, remove_z=False, remove_m=False):
        """
        Repairs geometry and removes ZM coords if requested
        If removing Z or M geometry, a copy will be created in a
        File Geodatabase.
        :return:
        """
        try:
            result = arcpy.RepairGeometry_management(fc)
        except arcpy.ExecuteError:
            logger.error('%s is locked.' % fc)
            return
        if result.maxSeverity == 0:
            logger.info('No geometry problems in %s' % fc)
        elif result.maxSeverity == 1:
            logger.info('Repaired %s geometry problems' % result.messageCount)
        else:
            logger.warn('Repair geometry failed on %s' % fc)

        zm_copy = ''
        if remove_z and arcpy.Describe(fc).hasZ:
            arcpy.env.outputZFlag = "Disabled"
            zm_copy += 'z'
        if remove_m and arcpy.Describe(fc).hasM:
            arcpy.env.outputMFlag = "Disabled"
            zm_copy += 'm'
        if zm_copy:
            # Make a copy of feature class with this geom removed
            logger.info('Removing %s geometry:' % zm_copy)
            pathname = os.path.dirname(fc)
            basename = os.path.basename(fc).lower().replace('.shp', '')
            if pathname.endswith('.gdb') and \
                self.arctools.checkFileGDBIntegrity(pathname):
                output_gdb = pathname
            else:
                gdb_name = 'RemoveZM.gdb'
                output_gdb = os.path.join(pathname, gdb_name)
                self.arctools.newFileGDB(pathname, gdb_name)

            output_fc = basename + '_no_' + zm_copy
            output_no_zm = os.path.join(output_gdb, output_fc)
            # If output already exists, add a timestamp to avoid collision
            if arcpy.Exists(output_no_zm):
                output_fc += '_' + logger.getTS()
                output_no_zm = os.path.join(output_gdb, output_fc)
            result = arcpy.FeatureClassToFeatureClass_conversion(fc, output_gdb, output_fc)
            if not result.status == 4:
                logger.warn('Cannot make a copy in %s' % output_no_zm)
                return
            logger.info('Copied to %s with %s geometry removed.' % (output_no_zm, zm_copy))

    def feature_complexity(self, fc, vertex_limit=30000, part_limit=1000):
        """
        Checks for excessively complex or large multi-part features
        Optional user-specified parameters. Default is reasonably conservative
        to warn users about potential problems in geoprocessing.
        :return:
        """
        vertex_overlimit = 0
        part_overlimit = 0
        vertex_max = 0
        part_max = 0
        logger.info('Checking %s features in %s' % (
            self.arctools.getCount(fc), fc))
        with arcpy.da.SearchCursor(fc, ['SHAPE@']) as c:
            for row in c:
                geom = row[0]
                if geom is not None:
                    parts = geom.partCount
                    if parts > part_max:
                        part_max = geom.partCount
                    if parts > part_limit:
                        part_overlimit += 1
                    if geom.pointCount > vertex_max:
                        vertex_max = geom.pointCount
                    if geom.pointCount > vertex_limit:
                        vertex_overlimit += 1
        if vertex_overlimit:
            logger.warn('%s complex features with more than %s vertices.' % (
                vertex_overlimit, vertex_limit))
        if part_overlimit:
            logger.warn('%s features with more than %s parts.' % (
                part_overlimit, part_limit))
        if vertex_overlimit or part_overlimit:
            logger.info('Tips to reduce complex features: http://arcg.is/2pRuAk9')
        else:
            logger.info('No excessively complex features.')
        logger.info('Maximum vertex count: %s, part count %s' % (vertex_max, part_max))

    def duplicates(self, fc):
        """
        Checks for table rows with duplicate attributes or duplicate
        geometry. For table rows: hash the tuple in a dict.
        For geom: hash the WKT geometry
        :return:
        """
        # Duplicate attributes: all fields except OID, SHAPE
        # Duplicate geom: SHAPE
        import hashlib
        fields = self.arctools.getFieldNames(fc)
        oid_field = arcpy.Describe(fc).OIDFieldName
        geom_field = arcpy.Describe(fc).SHAPEFieldName
        if oid_field in fields:
            fields.remove(oid_field)
        if geom_field in fields:
            fields.remove(geom_field)

        # Check for duplicate attributes
        logger.info('Checking for duplicate attributes in %s' % fc)
        collisions = defaultdict(int)
        with arcpy.da.SearchCursor(fc, fields) as c:
            for row in c:
                # hash = hashlib.md5(row).hexdigest()
                collisions[row] += 1
        has_dup = False
        for (row, count) in collisions.items():
            if count > 1:
                logger.warn('%s rows with duplicate attributes: %s' % (count, list(row)))
                has_dup = True
        if not has_dup:
            logger.info('No duplicate attributes found.')

        # Check geometry
        logger.info('Checking for duplicate gemeotry in %s' % fc)
        fields = [oid_field, "SHAPE@WKT"]
        collisions = defaultdict(list)
        with arcpy.da.SearchCursor(fc, fields) as c:
            for row in c:
                oid = row[0]
                try:
                    geom_wkt = row[1]
                except:  # If we cannot make a WKT representation
                    continue
                # Hash to avoid huge strings blowing up memory use
                hash = hashlib.md5(geom_wkt).hexdigest()
                collisions[hash].append(oid)
        has_dup = False
        for (hash, oid_list) in collisions.items():
            if len(oid_list) > 1:
                logger.warn('%s duplicate geometries in OIDs: %s' % (len(oid_list), oid_list))
                has_dup = True
        if not has_dup:
            logger.info('No duplicate geometries found.')
