import arcpy
import arcsupport
import logs
arctools = arcsupport.ArcTools(silent=True)
logger = logs.ArcLogger()
qctool = arcsupport.QualityControl()


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Quality Report"
        self.alias = "Quality Report"

        # List of tool classes associated with this toolbox
        self.tools = [Tool]


class Tool(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Quality Report Tool"
        self.description = "Provides a report on the completeness and structural quality of spatial and attribute data."
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""
        params = []
        dataset = arcpy.Parameter(
            displayName="Dataset(s) to validate",
            name="dataset",
            datatype=["DEFeatureClass", "DEWorkspace"],
            parameterType="Required",
            direction="Input"
        )
        params.append(dataset)
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        dataset = parameters[0].valueAsText
        # arcpy.AddMessage('arcpy %s' % dataset)
        # logger.arcMessage('logger %s' % dataset)
        logger.info('Running quality report on: %s' % dataset)
        qctool.qc_report(dataset)
        return
