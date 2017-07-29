# arcgis-support

Extends arcpy with various high-level GIS functions.

## Installation

Clone this repository to a local disk. Add the folder arcgis-support to pythonpath.

## Requirements

This module extends and makes extensive use of ESRI's arcpy module:
http://desktop.arcgis.com/en/arcmap/latest/analyze/arcpy/what-is-arcpy-.htm

## Description

arcsupport.py library contains three classes with high-level functions that are
inconvenient to use or not available in ESRI's arcpy module.
1. The ArcTools class provides support functions and workarounds for various
common arcpy programming tasks that are inconvenient or poorly-implemented in the
"out-of-the-box" version of arcpy.
2. The GeomTools class provides some geometry processing tools that are
not available by default in arcpy, or require a Standard / Advanced license.
3. QualityControl class provides tools to check attribute and geometry
quality of feature classes and tables.

logs.py library is a wrapper around the standard Python logger with support
for arcpy logger (displays messages in the Results window).
