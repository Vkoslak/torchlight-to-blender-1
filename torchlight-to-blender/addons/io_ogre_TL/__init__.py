# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8-80 compliant>

"""
Name: 'OGRE for Torchlight 2(*.MESH)'
Blender: 2.59, 2.62, 2.63a, 2.77a, 2.79
Group: 'Import/Export'
Tooltip: 'Import/Export Torchlight 2 OGRE mesh files'

Author: Rob James
Original Author: Dusho

There were some great updates added to a forked version of this script
for a game called Kenshi by "someone".
I'm attempting to put the relevent changes into the plugin to improve
Torchlight editing.

Thanks goes to 'goatman' for his port of Ogre export script from 2.49b to 2.5x,
and 'CCCenturion' for trying to refactor the code to be nicer (to be included)

"""

__author__ = "Rob James"
__version__ = "0.7.1 09-May-2017"

__bpydoc__ = """\
This script imports/exports Torchlight Ogre models into/from Blender.

Supported:<br>
    * import/export of basic meshes
    * import of skeleton
    * import/export of vertex weights
      (ability to import characters and adjust rigs)
    * export of vertex colour (RGB)
    * Calculation of tangents and binormals for export

Missing:<br>
    * skeletons (export)
    * animations
    * shape keys

Known issues:<br>
    * imported materials will loose certain informations not applicable
      to Blender when exported

History:<br>
    * v0.7.2   (08-Dec-2016) - fixed divide by 0 error calculating tangents.
             From Kenshi addon
    * v0.7.1   (07-Sep-2016) - bug fixes. From Kenshi addon
    * v0.7.0   (02-Sep-2016) - Persistant Ogre bone IDs, Export vertex colours.
             Generates tangents and binormals. From Kenshi addon
    * v0.6.4   (25-Mar-2017) - BUGFIX: By material was breaking armor sets
    * v0.6.3   (01-Jan-2017) - I'm not Dusho, but I added ability to export
             multiple materials and textures on a single mesh.
    * v0.6.2   (09-Mar-2013) - bug fixes (working with materials+textures),
             added 'Apply modifiers' and 'Copy textures'
    * v0.6.1   (27-Sep-2012) - updated to work with Blender 2.63a
    * v0.6     (01-Sep-2012) - added skeleton import + vertex weights
             import/export
    * v0.5     (06-Mar-2012) - added material import/export
    * v0.4.1   (29-Feb-2012) - flag for applying transformation, default=true
    * v0.4     (28-Feb-2012) - fixing export when no UV data are present
    * v0.3     (22-Feb-2012) - WIP - started cleaning + using OgreXMLConverter
    * v0.2     (19-Feb-2012) - WIP - working export of geometry and faces
    * v0.1     (18-Feb-2012) - initial 2.59 import code (from .xml)
    * v0.0     (12-Feb-2012) - file created
"""

bl_info = {
    "name": "Torchlight 2 MESH format",
    "author": "Rob James",
    "blender": (2, 5, 9),
    "api": 35622,
    "location": "File > Import-Export",
    "description": ("Import-Export Torchlight 2 Model, Import MESH, UV's, "
                    "materials and textures"),
    "warning": "",
    "wiki_url": ("https://github.com/RobJames-Texas/torchlight-to-blender"),
    "tracker_url": "https://github.com/RobJames-Texas/torchlight-to-blender",
    "support": 'OFFICIAL',
    "category": "Import-Export"}

if "bpy" in locals():
    import imp
    if "TLImport" in locals():
        imp.reload(TLImport)
    if "TLExport" in locals():
        imp.reload(TLExport)

import bpy
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       )
from bpy_extras.io_utils import (ExportHelper,
                                 ImportHelper,
                                 path_reference_mode,
                                 axis_conversion,
                                 )


# Path for your OgreXmlConverter
OGRE_XML_CONVERTER = "OgreXMLConverter.exe"


def findConverter(p):
    import os

    # Full path exists
    if os.path.isfile(p):
        return p

    # Look in script directory
    scriptPath = os.path.dirname(os.path.realpath(__file__))
    sp = os.path.join(scriptPath, p)
    if os.path.isfile(sp):
        return sp

    # Fail
    print('Could not find xml converter', p)
    return None


class ImportTL(bpy.types.Operator, ImportHelper):
    '''Load a Torchlight MESH File'''
    bl_idname = "import_scene.mesh"
    bl_label = "Import MESH"
    bl_options = {'PRESET'}

    filename_ext = ".mesh"

    keep_xml = BoolProperty(
            name="Keep XML",
            description="Keeps the XML file when converting from .MESH",
            default=False,
            )

    filter_glob = StringProperty(
            default="*.mesh;*.MESH;.xml;.XML",
            options={'HIDDEN'},
            )

    xml_converter = StringProperty(
            name="XML Converter",
            description="Ogre XML Converter program for converting between .MESH files and .XML files",
            default=OGRE_XML_CONVERTER
            )

    def execute(self, context):
        # print("Selected: " + context.active_object.name)
        from . import TLImport

        keywords = self.as_keywords(ignore=("filter_glob",))
        keywords['xml_converter'] = findConverter(keywords['xml_converter'])

        print('converter', keywords['xml_converter'])

        return TLImport.load(self, context, **keywords)

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.prop(self, "xml_converter")

        row = layout.row(align=True)
        row.prop(self, "keep_xml")


class ExportTL(bpy.types.Operator, ExportHelper):
    '''Export a Torchlight MESH File'''

    bl_idname = "export_scene.mesh"
    bl_label = 'Export MESH'
    bl_options = {'PRESET'}

    filename_ext = ".mesh"

    xml_converter = StringProperty(
            name="XML Converter",
            description="Ogre XML Converter program for converting between .MESH files and .XML files",
            default=OGRE_XML_CONVERTER,
            )

    export_tangents = BoolProperty(
            name="Export tangents",
            description="Export tangent data for the mesh",
            default=False,
            )
    tangent_parity = BoolProperty(
            name="   Parity in W",
            description="Tangents have parity stored in the W component",
            default=False,
            )

    export_binormals = BoolProperty(
            name="Export Binormals",
            description="Generate binormals for the mesh",
            default=False,
            )

    export_colour = BoolProperty(
            name="Export colour",
            description="Export vertex colour data",
            default=False,
            )

    enable_by_material = BoolProperty(
            name="Enable By Material",
            description="Multiple materials on a mesh will be exported as submeshes.",
            default=False,
            )

    keep_xml = BoolProperty(
            name="Keep XML",
            description="Keeps the XML file when converting to .MESH",
            default=False,
            )

    apply_transform = BoolProperty(
            name="Apply Transform",
            description="Applies object's transformation to its data",
            default=False,
            )

    apply_modifiers = BoolProperty(
            name="Apply Modifiers",
            description="Applies modifiers",
            default=False,
            )

    overwrite_material = BoolProperty(
            name="Overwrite .material",
            description="Overwrites existing .material file, if present.",
            default=False,
            )

    copy_textures = BoolProperty(
            name="Copy textures",
            description="Copies material source textures to material file location",
            default=False,
            )

    export_and_link_skeleton = BoolProperty(
            name="Export .skeleton and link",
            description="Exports new skeleton and links the mesh to this new skeleton.\nLeave off to link with existing skeleton if applicable.",
            default=False,
            )

    filter_glob = StringProperty(
            default="*.mesh;*.MESH;.xml;.XML",
            options={'HIDDEN'},
            )

    def execute(self, context):
        from . import TLExport
        from mathutils import Matrix

        keywords = self.as_keywords(ignore=("check_existing", "filter_glob"))
        keywords['xml_converter'] = findConverter(keywords['xml_converter'])

        return TLExport.save(self, context, **keywords)

    def draw(self, context):
        layout = self.layout

        row = layout.row(align=True)
        row.prop(self, "xml_converter")

        row = layout.row(align=True)
        row.prop(self, "enable_by_material")

        row = layout.row(align=True)
        row.prop(self, "keep_xml")

        row = layout.row(align=True)
        row.prop(self, "export_tangents")

        row = layout.row(align=True)
        row.prop(self, "export_binormals")

        row = layout.row(align=True)
        row.prop(self, "export_colour")

        row = layout.row(align=True)
        row.prop(self, "apply_transform")

        row = layout.row(align=True)
        row.prop(self, "apply_modifiers")

        row = layout.row(align=True)
        row.prop(self, "overwrite_material")

        row = layout.row(align=True)
        row.prop(self, "copy_textures")

        row = layout.row(align=True)
        row.prop(self, "export_and_link_skeleton")


def menu_func_import(self, context):
    self.layout.operator(ImportTL.bl_idname, text="Torchlight OGRE (.mesh)")


def menu_func_export(self, context):
    self.layout.operator(ExportTL.bl_idname, text="Torchlight OGRE (.mesh)")


def register():
    bpy.utils.register_module(__name__)

    bpy.types.INFO_MT_file_import.append(menu_func_import)
    bpy.types.INFO_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_module(__name__)

    bpy.types.INFO_MT_file_import.remove(menu_func_import)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()
