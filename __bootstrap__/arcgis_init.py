from __future__ import division
import os,sys,socket,shutil,math,io,re,datetime,traceback,codecs,json,random,imp,logging
from random import randint
from collections import defaultdict
import arcsupport;import arcpy;import os,sys,io,json;reload(arcsupport);a = arcsupport.ArcTools();gt = arcsupport.GeomTools();qc=arcsupport.QualityControl();g = arcpy.Geometry();srWGS84 = a.createSRObject('WKID', 4326);srWebMercator = a.createSRObject('WKID', 3857);arcpy.env.overwriteOutput=True