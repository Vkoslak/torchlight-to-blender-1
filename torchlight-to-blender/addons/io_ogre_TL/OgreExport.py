#!BPY

"""
Name: 'OGRE for Torchlight 2 (*.MESH)'
Blender: 2.59, 2.62, 2.63a, 2.78c
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
__version__ = "0.8.5 02-Jan-2018"

__bpydoc__ = """\
This script imports/exports Torchlight Ogre models into/from Blender.

Supported:<br>
    * import/export of basic meshes
    * import/export of skeleton
    * import/export of animations
    * import/export of vertex weights (ability to import characters and
      adjust rigs)
    * import/export of vertex colour (RGB)
    * import/export of vertex alpha (Uses second vertex colour
      layer called Alpha)
    * import/export of shape keys
    * Calculation of tangents and binormals for export

Known issues:<br>
    * imported materials will loose certain informations not applicable to
      Blender when exported
    * UVs can appear messed up when exporting non-trianglulated meshes

History:<br>
    * v0.8.5   (02-Jan-2018) - Optimisation: Use hashmap for duplicate
             vertex detection From Kenshi add on
    * v0.8.4   (20-Nov-2017) - Fixed animation quaternion interpolation
             From Kenshi addon
    * v0.8.3   (06-Nov-2017) - Warning when linked skeleton file not found
             From Kenshi addon
    * v0.8.2   (25-Sep-2017) - Fixed bone translations in animations
             From Kenshi addon
    * v0.8.1   (28-Jul-2017) - Added alpha component to vertex colour
             From Kenshi addon
    * v0.8.0   (30-Jun-2017) - Added animation and shape key support.
             Rewritten skeleton export. From Kenshi addon
    * v0.7.2   (08-Dec-2016) - fixed divide by 0 error calculating tangents.
             From Kenshi addon
    * v0.7.1   (07-Sep-2016) - bug fixes. From Kenshi addon
    * v0.7.0   (02-Sep-2016) - Persistant Ogre bone IDs, Export vertex colours.
             Generates tangents and binormals. From Kenshi addon
    * v0.6.5   (09-May-2017) - BUGFIX: Mesh with no bone assignment would
             not export.
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

# from Blender import *
from xml.dom import minidom
import bpy
from mathutils import Vector, Matrix
import math
import os
import subprocess
import shutil

SHOW_EXPORT_DUMPS = False
SHOW_EXPORT_TRACE = False
SHOW_EXPORT_TRACE_VX = False

# default blender version of script
blender_version = 259


def hash_combine(x, y):
    return x ^ y + 0x9e3779b9 + (x << 6) + (x >> 2)


class VertexInfo(object):
    def __init__(self, px, py, pz,
                 nx, ny, nz,
                 u, v,
                 r, g, b, a,
                 boneWeights, original):
        self.px = px
        self.py = py
        self.pz = pz
        self.nx = nx
        self.ny = ny
        self.nz = nz
        self.u = u
        self.v = v
        self.r = r
        self.g = g
        self.b = b
        self.a = a
        self.boneWeights = boneWeights
        self.original = original

    '''does not compare ogre_vidx (and position at the moment)
      [ no need to compare position ]'''
    def __eq__(self, o):
        if self.nx != o.nx or self.ny != o.ny or self.nz != o.nz:
            return False
        elif self.px != o.px or self.py != o.py or self.pz != o.pz:
            return False
        elif self.u != o.u or self.v != o.v:
            return False
        elif self.r != o.r or self.g != o.g or self.b != o.b:
            return False
        return True

    def __hash__(self):
        result = hash(self.px)
        result = hash_combine(result, hash(self.py))
        result = hash_combine(result, hash(self.pz))
        result = hash_combine(result, hash(self.nx))
        result = hash_combine(result, hash(self.ny))
        result = hash_combine(result, hash(self.nz))
        result = hash_combine(result, hash(self.u))
        result = hash_combine(result, hash(self.v))
        result = hash_combine(result, hash(self.r))
        result = hash_combine(result, hash(self.g))
        result = hash_combine(result, hash(self.b))
        return result


########################################

class Skeleton(object):
    def __init__(self, ob):
        self.armature = ob.find_armature()
        self.name = self.armature.name
        self.ids = {}
        self.hidden = self.armature.hide
        data = self.armature.data
        self.armature.hide = False

        # get ogre bone ids - need to be in edit mode to access edit_bones
        prev = bpy.context.scene.objects.active
        bpy.context.scene.objects.active = self.armature
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        for bone in data.edit_bones:
            if 'OGREID' in bone:
                self.ids[bone.name] = bone['OGREID']

        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        bpy.context.scene.objects.active = prev
        self.armature.hide = self.hidden

        # Allocate bone ids
        index = 0
        missing = []
        self.bones = [None] * len(data.bones)
        for bone in data.bones:
            if bone.name in self.ids:
                self.bones[self.ids[bone.name]] = bone
            else:
                missing.append(bone)
        for bone in missing:
            while self.bones[index]:
                index += 1
            self.bones[index] = bone
            self.ids[bone.name] = index

        # calculate bone rest matrices
        rot = Matrix.Rotation(-1.5707963, 4, 'X')  # Rotate to y-up coordinates
        fix = Matrix.Rotation(1.5707963, 4, 'Z')   # Fix bone axis
        fix *= Matrix.Rotation(3.141592653, 4, 'X')
        self.rest = [None] * len(self.bones)
        for i, bone in enumerate(self.bones):
            if bone.parent:
                self.rest[i] = (bone.parent.matrix_local *
                                fix * rot).inverted()\
                                     * bone.matrix_local * fix * rot
            else:
                self.rest[i] = rot * bone.matrix_local * fix * rot

    def bone_id(self, name):
        return self.ids[name]

    def export_xml(self, doc, root):
        bones = doc.createElement('bones')
        root.appendChild(bones)
        bh = doc.createElement('bonehierarchy')
        root.appendChild(bh)

        for i, bone in enumerate(self.bones):
            b = doc.createElement('bone')
            b.setAttribute('name', bone.name)
            b.setAttribute('id', str(i))
            bones.appendChild(b)

            if bone.parent:
                bp = doc.createElement('boneparent')
                bp.setAttribute('bone', bone.name)
                bp.setAttribute('parent', bone.parent.name)
                bh.appendChild(bp)

            mat = self.rest[i]
            pos = doc.createElement('position')
            b.appendChild(pos)

            x, y, z = mat.to_translation()
            pos.setAttribute('x', '%6f' % x)
            pos.setAttribute('y', '%6f' % y)
            pos.setAttribute('z', '%6f' % z)

            rot = doc.createElement('rotation')
            b.appendChild(rot)

            q = mat.to_quaternion()
            rot.setAttribute('angle', '%6f' % q.angle)
            axis = doc.createElement('axis')
            rot.appendChild(axis)

            x, y, z = q.axis
            axis.setAttribute('x', '%6f' % x)
            axis.setAttribute('y', '%6f' % y)
            axis.setAttribute('z', '%6f' % z)

#########################################


def bCollectAnimationData(meshData):
    if 'skeleton' not in meshData:
        return
    armature = meshData['skeleton'].armature
    animdata = armature.animation_data
    if animdata:
        actions = []
        # Current action
        if animdata.action:
            actions.append(animdata.action)
        # actions in NLA
        if animdata.nla_tracks:
            for track in animdata.nla_tracks.values():
                for strip in track.strips.values():
                    if strip.action and strip.action not in actions:
                        actions.append(strip.action)

        # Export them all
        scene = bpy.context.scene
        currentFrame = scene.frame_current
        currentAction = animdata.action
        meshData['animations'] = []
        for act in actions:
            print('Action', act.name)
            animdata.action = act
            animation = {}
            animation['keyframes'] = collectAnimationData(armature,
                                                          act.frame_range,
                                                          scene.render.fps,
                                                          scene.frame_step)
            animation['name'] = act.name
            animation['length'] = (act.frame_range[1] -
                                   act.frame_range[0]) / scene.render.fps
            meshData['animations'].append(animation)

        animdata.action = currentAction
        scene.frame_set(currentFrame)


def collectAnimationData(armature, frame_range, fps, step=1):
    scene = bpy.context.scene
    start, end = frame_range

    keyframes = {}
    for bone in armature.pose.bones:
        keyframes[bone.name] = [[], [], []]   # pos, rot, scl

    fix1 = Matrix([(1, 0, 0), (0, 0, 1), (0, -1, 0)])  # swap YZ & negate some
    fix2 = Matrix([(0, 1, 0), (0, 0, 1), (1, 0, 0)])

    # Get base matrices
    mat = {}
    hidden = armature.hide
    armature.hide = False
    prev = bpy.context.scene.objects.active
    bpy.context.scene.objects.active = armature
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    for b in armature.data.edit_bones:
        if b.parent:
            mat[b.name] = fix2 * \
             b.parent.matrix.to_3x3().transposed() * \
             b.matrix.to_3x3()
        else:
            mat[b.name] = fix1 * b.matrix.to_3x3()
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    bpy.context.scene.objects.active = prev
    armature.hide = hidden

    # Collect data
    for frame in range(int(start), int(end)+1, step):
        time = (frame - start) / fps
        bpy.context.scene.frame_set(frame)
        for bone in armature.pose.bones:
            loc = bone.location
            rot = bone.rotation_quaternion
            scl = bone.scale

            # transform transation into parent coordinates
            loc = mat[bone.name] * loc

            keyframes[bone.name][0].append((time, (loc[0], loc[1], loc[2])))
            keyframes[bone.name][1].append((time, (rot[0], rot[1], rot[2], rot[3])))
            keyframes[bone.name][2].append((time, (scl[0], scl[1], scl[2])))

    # Remove unnessesary tracks
    identity = [(0, 0, 0), (1, 0, 0, 0), (1, 1, 1)]
    for bone, data in keyframes.items():
        for track in range(3):
            used = False
            for key in data[track]:
                if used:
                    break
                for i in range(len(identity[track])):
                    if abs(key[1][i] - identity[track][i]) > 1e-5:
                        used = True
                        break
            if not used:
                data[track] = []

        # Delete whole track if unused
        if not (data[0] or data[1] or data[2]):
            keyframes[bone] = None

    return keyframes


def xSaveAnimations(meshData, xNode, xDoc):
    if 'animations' in meshData:
        animations = xDoc.createElement("animations")
        xNode.appendChild(animations)

        for animation in meshData['animations']:
            xSaveAnimation(animation, xDoc, animations)


def xSaveAnimation(animation, xDoc, xAnimations):
    anim = xDoc.createElement('animation')
    tracks = xDoc.createElement('tracks')
    xAnimations.appendChild(anim)
    anim.appendChild(tracks)
    anim.setAttribute('name', animation['name'])
    anim.setAttribute('length', '%6f' % animation['length'])
    keyframes = animation['keyframes']
    for bone, data in keyframes.items():
        if not data:
            continue
        track = xDoc.createElement('track')
        keyframes = xDoc.createElement('keyframes')
        track.setAttribute('bone', bone)
        tracks.appendChild(track)
        track.appendChild(keyframes)

        basis = 0 if data[0] else 1 if data[1] else 2

        for frame in range(len(data[basis])):
            keyframe = xDoc.createElement('keyframe')
            keyframes.appendChild(keyframe)
            keyframe.setAttribute('time', '%6f' % data[basis][frame][0])

            if data[0]:
                loc = data[0][frame][1]
                translate = xDoc.createElement('translate')
                translate.setAttribute('x', '%6f' % loc[0])
                translate.setAttribute('y', '%6f' % loc[1])
                translate.setAttribute('z', '%6f' % loc[2])
                keyframe.appendChild(translate)

            if data[1]:
                rot = data[1][frame][1]
                angle = math.acos(rot[0]) * 2
                l = math.sqrt(rot[1]*rot[1] + rot[2]*rot[2] + rot[3]*rot[3])
                axis = (1, 0, 0) if l == 0 else (rot[1]/l, rot[2]/l, rot[3]/l)

                rotate = xDoc.createElement('rotate')
                raxis = xDoc.createElement('axis')
                rotate.setAttribute('angle', '%6f' % angle)
                raxis.setAttribute('x', '%6f' % axis[1])
                raxis.setAttribute('y', '%6f' % axis[2])
                raxis.setAttribute('z', '%6f' % axis[0])
                keyframe.appendChild(rotate)
                rotate.appendChild(raxis)

            if data[2]:
                scl = data[2][frame][1]
                scale = xDoc.createElement('scale')
                scale.setAttribute('x', '%6f' % -loc[0])
                scale.setAttribute('y', '%6f' % loc[2])
                scale.setAttribute('z', '%6f' % loc[1])
                keyframe.appendChild(scale)


#########################################


def fileExist(filepath):
    try:
        filein = open(filepath)
        filein.close()
        return True
    except:
        print("No file: ", filepath)
        return False


def toFmtStr(number):
    # return str("%0.7f" % number)
    return str(round(number, 7))


def indent(indent):
    """Indentation.

       @param indent Level of indentation.
       @return String.
    """
    return "        "*indent


def xSaveGeometry(geometry, xDoc, xMesh):
    # I guess positions (vertices) must be there always
    vertices = geometry['positions']

    geometryType = "geometry"

    isNormals = False
    if 'normals' in geometry:
        isNormals = True
        normals = geometry['normals']

    isTexCoordsSets = False
    texCoordSets = geometry['texcoordsets']
    if texCoordSets > 0 and 'uvsets' in geometry:
        isTexCoordsSets = True
        uvSets = geometry['uvsets']

    isColours = False
    if 'colours' in geometry:
        isColours = True
        colours = geometry['colours']

    isTangents = False
    if 'tangents' in geometry:
        isTangents = True
        tangents = geometry['tangents']

    isBinormals = False
    if 'binormals' in geometry:
        isBinormals = True
        binormals = geometry['binormals']

    xGeometry = xDoc.createElement(geometryType)
    xGeometry.setAttribute("vertexcount", str(len(vertices)))
    xMesh.appendChild(xGeometry)

    xVertexBuffer = xDoc.createElement("vertexbuffer")
    xVertexBuffer.setAttribute("positions", "true")
    if isNormals:
        xVertexBuffer.setAttribute("normals", "true")
    if isTexCoordsSets:
        xVertexBuffer.setAttribute("texture_coord_dimensions_0", "2")
        xVertexBuffer.setAttribute("texture_coords", str(texCoordSets))

    if isColours:
        xVertexBuffer.setAttribute("colours_diffuse", "true")
    if isTangents:
        xVertexBuffer.setAttribute("tangents", "true")
    if isBinormals:
        xVertexBuffer.setAttribute("binormals", "true")

    xGeometry.appendChild(xVertexBuffer)

    for i, vx in enumerate(vertices):
        xVertex = xDoc.createElement("vertex")
        xVertexBuffer.appendChild(xVertex)
        xPosition = xDoc.createElement("position")
        xPosition.setAttribute("x", toFmtStr(vx[0]))
        xPosition.setAttribute("y", toFmtStr(vx[2]))
        xPosition.setAttribute("z", toFmtStr(-vx[1]))
        xVertex.appendChild(xPosition)

        if isNormals:
            xNormal = xDoc.createElement("normal")
            xNormal.setAttribute("x", toFmtStr(normals[i][0]))
            xNormal.setAttribute("y", toFmtStr(normals[i][2]))
            xNormal.setAttribute("z", toFmtStr(-normals[i][1]))
            xVertex.appendChild(xNormal)

        if isTexCoordsSets:
            xUVSet = xDoc.createElement("texcoord")
            # take only 1st set for now
            xUVSet.setAttribute("u", toFmtStr(uvSets[i][0][0]))
            xUVSet.setAttribute("v", toFmtStr(1.0 - uvSets[i][0][1]))
            xVertex.appendChild(xUVSet)

        if isColours:
            xColour = xDoc.createElement("colour_diffuse")
            xColour.setAttribute("value", '%g %g %g, %g' %
                                 (colours[i][0], colours[i][1],
                                  colours[i][2], colours[i][3]))
            xVertex.appendChild(xColour)

        if isTangents:
            xTangent = xDoc.createElement("tangent")
            xTangent.setAttribute("x", toFmtStr(tangents[i][0]))
            xTangent.setAttribute("y", toFmtStr(tangents[i][2]))
            xTangent.setAttribute("z", toFmtStr(-tangents[i][1]))
            xVertex.appendChild(xTangent)

        if isBinormals:
            xBinormal = xDoc.createElement("binormal")
            xBinormal.setAttribute("x", toFmtStr(binormals[i][0]))
            xBinormal.setAttribute("y", toFmtStr(binormals[i][2]))
            xBinormal.setAttribute("z", toFmtStr(-binormals[i][1]))
            xVertex.appendChild(xBinormal)


def xSaveSubMeshes(meshData, xDoc, xMesh, hasSharedGeometry=False):
    xSubMeshes = xDoc.createElement("submeshes")
    xMesh.appendChild(xSubMeshes)

    for submesh in meshData['submeshes']:
        xSubMesh = xDoc.createElement("submesh")
        xSubMesh.setAttribute("material", submesh['material'])
        numVerts = len(submesh['geometry']['positions'])
        xSubMesh.setAttribute("usesharedvertices", "false")
        xSubMesh.setAttribute("use32bitindexes", str(bool(numVerts > 65535)))
        xSubMesh.setAttribute("operationtype", "triangle_list")
        xSubMeshes.appendChild(xSubMesh)
        # write all faces
        if 'faces' in submesh:
            faces = submesh['faces']
            xFaces = xDoc.createElement("faces")
            xFaces.setAttribute("count", str(len(faces)))
            xSubMesh.appendChild(xFaces)
            for face in faces:
                xFace = xDoc.createElement("face")
                xFace.setAttribute("v1", str(face[0]))
                xFace.setAttribute("v2", str(face[1]))
                xFace.setAttribute("v3", str(face[2]))
                xFaces.appendChild(xFace)
        # if there is geometry per sub mesh
        if 'geometry' in submesh:
            geometry = submesh['geometry']
            xSaveGeometry(geometry, xDoc, xSubMesh)
        # boneassignments
        if 'skeleton' in meshData:
            skeleton = meshData['skeleton']
            # xBoneAssignments = xGetBoneAssignments(meshData, xDoc,
            #  submesh['geometry']['boneassignments'])
            xBoneAssignments = xDoc.createElement("boneassignments")
            for vxIdx, vxBoneAsg in enumerate(submesh['geometry']['boneassignments']):
                for boneAndWeight in vxBoneAsg:
                    boneName = boneAndWeight[0]
                    boneWeight = boneAndWeight[1]
                    xVxBoneassignment = xDoc.createElement("vertexboneassignment")
                    xVxBoneassignment.setAttribute("vertexindex", str(vxIdx))
                    xVxBoneassignment.setAttribute("boneindex", str(skeleton.bone_id(boneName)))
                    xVxBoneassignment.setAttribute("weight", '%6f' % boneWeight)
                    xBoneAssignments.appendChild(xVxBoneassignment)
            xSubMesh.appendChild(xBoneAssignments)


def xSavePoses(meshData, xDoc, xMesh):
    xPoses = xDoc.createElement("poses")
    xMesh.appendChild(xPoses)
    for index, submesh in enumerate(meshData['submeshes']):
        if not submesh['poses']:
            continue
        for name in submesh['poses']:
            xPose = xDoc.createElement("pose")
            xPose.setAttribute('target', 'submesh')
            xPose.setAttribute('index', str(index))
            xPose.setAttribute('name', name)
            xPoses.appendChild(xPose)
            pose = submesh['poses'][name]
            for v in pose:
                xPoseVertex = xDoc.createElement('poseoffset')
                xPoseVertex.setAttribute('index', str(v[0]))
                xPoseVertex.setAttribute('x', '%6f' % v[1])
                xPoseVertex.setAttribute('y', '%6f' % v[3])
                xPoseVertex.setAttribute('z', '%6f' % -v[2])
                xPose.appendChild(xPoseVertex)


def xSaveSkeletonData(blenderMeshData, filepath):
    from xml.dom.minidom import Document
    if 'skeleton' in blenderMeshData:
        skeleton = blenderMeshData['skeleton']

        xDoc = Document()
        xRoot = xDoc.createElement("skeleton")
        xDoc.appendChild(xRoot)
        skeleton.export_xml(xDoc, xRoot)

        if 'animations' in blenderMeshData:
            xSaveAnimations(blenderMeshData, xRoot, xDoc)

        # xmlfile = os.path.join(filepath, '%s.skeleton.xml' %name )
        nameOnly = os.path.splitext(filepath)[0]  # removing .mesh
        xmlfile = nameOnly + ".skeleton.xml"
        data = xDoc.toprettyxml(indent='    ')
        f = open(xmlfile, 'wb')
        f.write(bytes(data, 'utf-8'))
        f.close()


def xSaveMeshData(meshData, filepath, export_skeleton):
    from xml.dom.minidom import Document

    hasSharedGeometry = False
#   Torchlight does not like shared geometry
#    if 'sharedgeometry' in meshData:
#        hasSharedGeometry = True

    # Create the minidom document
    print("Creating " + filepath + ".xml")
    xDoc = Document()

    xMesh = xDoc.createElement("mesh")
    xDoc.appendChild(xMesh)

    if hasSharedGeometry:
        geometry = meshData['sharedgeometry']
        xSaveGeometry(geometry, xDoc, xMesh, hasSharedGeometry)

    xSaveSubMeshes(meshData, xDoc, xMesh, hasSharedGeometry)

    if 'has_poses' in meshData:
        xSavePoses(meshData, xDoc, xMesh)

    # skeleton link only
    if 'skeleton' in meshData:
        xSkeletonlink = xDoc.createElement("skeletonlink")
        # default skeleton
        linkSkeletonName = meshData['skeleton'].name
        if export_skeleton:
            nameDotMeshDotXml = os.path.split(filepath)[1].lower()
            nameDotMesh = os.path.splitext(nameDotMeshDotXml)[0]
            linkSkeletonName = os.path.splitext(nameDotMesh)[0]
        # xSkeletonlink.setAttribute("name", meshData['skeleton']['name']+".skeleton")
        xSkeletonlink.setAttribute("name", linkSkeletonName+".skeleton")
        xMesh.appendChild(xSkeletonlink)

    # Print our newly created XML
    fileWr = open(filepath + ".xml", 'w')
    fileWr.write(xDoc.toprettyxml(indent="    "))  # 4 spaces
    # doc.writexml(fileWr, "  ")
    fileWr.close()


def xSaveMaterialData(filepath, meshData, overwriteMaterialFlag, copyTextures):
    if 'materials' not in meshData:
        return

    allMatData = meshData['materials']

    if len(allMatData) <= 0:
        print('Mesh has no materials')
        return

    matFile = os.path.splitext(filepath)[0]  # removing .mesh
    matFile = matFile + ".material"
    print("material file: %s" % matFile)
    isMaterial = os.path.isfile(matFile)

    # if is no material file, or we are forced to overwrite it, write the material file
    if isMaterial is False or overwriteMaterialFlag is True:
        # write material
        fileWr = open(matFile, 'w')
        for matName, matInfo in allMatData.items():
            fileWr.write("material %s\n" % matName)
            fileWr.write("{\n")
            fileWr.write(indent(1) + "technique\n" + indent(1) + "{\n")
            fileWr.write(indent(2) + "pass\n" + indent(2) + "{\n")

            # write material content here
            fileWr.write(indent(3) + "ambient %f %f %f\n" % (matInfo['ambient'][0], matInfo['ambient'][1], matInfo['ambient'][2]))
            fileWr.write(indent(3) + "diffuse %f %f %f\n" % (matInfo['diffuse'][0], matInfo['diffuse'][1], matInfo['diffuse'][2]))
            fileWr.write(indent(3) + "specular %f %f %f 0\n" % (matInfo['specular'][0], matInfo['specular'][1], matInfo['specular'][2]))
            fileWr.write(indent(3) + "emissive %f %f %f\n" % (matInfo['emissive'][0], matInfo['emissive'][1], matInfo['emissive'][2]))

            if 'textures' in matInfo:
                for texInfo in matInfo['textures']:
                    fileWr.write(indent(3) + "texture_unit\n" + indent(3) + "{\n")
                    fileWr.write(indent(4) + "texture %s\n" % texInfo['texture'])
                    fileWr.write(indent(3) + "}\n")  # texture unit

            fileWr.write(indent(2) + "}\n")  # pass
            fileWr.write(indent(1) + "}\n")  # technique
            fileWr.write("}\n")

        fileWr.close()

    # try to copy material textures to destination
    if copyTextures:
        for matName, matInfo in allMatData.items():
            if 'texture' in matInfo:
                if 'texture_path' in matInfo:
                    srcTextureFile = matInfo['texture_path']
                    baseDirName = os.path.dirname(bpy.data.filepath)
                    if srcTextureFile[0:2] == "//":
                        print("Converting relative image name \"%s\"" % srcTextureFile)
                        srcTextureFile = os.path.join(baseDirName, srcTextureFile[2:])
                    if fileExist(srcTextureFile):
                        # copy texture to dir
                        print("Copying texture \"%s\"" % srcTextureFile)
                        try:
                            print(" to \"%s\"" % os.path.dirname(matFile))
                            shutil.copy(srcTextureFile, os.path.dirname(matFile))
                        except:
                            print("Error copying \"%s\"" % srcTextureFile)
                    else:
                        print("Can't copy texture \"%s\" because file does not exists!" % srcTextureFile)


def getVertexIndex(vertexInfo, vertexList):
    for vIdx, vert in enumerate(vertexList):
        if vertexInfo == vert:
            return vIdx

    # not present in list:
    vertexList.append(vertexInfo)
    return len(vertexList)-1


# Convert rgb colour to brightness value - used for alpha channel
def luminosity(c):
    return c[0] * 0.25 + c[1] * 0.5 + c[2] * 0.25


def bCollectMeshData(meshData, selectedObjects, applyModifiers,
                     exportColour, exportPoses):
    for ob in selectedObjects:
        # ob = bpy.types.Object ##
        materials = []
        for mat in ob.data.materials:
            if mat:
                materials.append(mat)
            else:
                print('[WARNING:] Bad material data in', ob)
                materials.append('_missing_material_')  # borrowed from ogre scene exporter

        if not materials:
            materials.append('_missing_material_')
        _sm_faces_ = []
        _sm_verts_ = []
        for matidx, mat in enumerate(materials):
            _sm_faces_.append([])
            _sm_verts_.append([])

        # mesh = bpy.types.Mesh ##
        if applyModifiers:
            mesh = ob.to_mesh(bpy.context.scene, True, 'PREVIEW')
        else:
            mesh = ob.data

        # blender 2.62 <-> 2.63 compatibility
        if blender_version <= 262:
            meshFaces = mesh.faces
            meshUV_textures = mesh.uv_textures
            meshVertex_colors = mesh.vertex_colors
        elif blender_version > 262:
            mesh.update(calc_tessface=True)
            meshFaces = mesh.tessfaces
            meshUV_textures = mesh.tessface_uv_textures
            meshVertex_colors = mesh.tessface_vertex_colors

        # first try to collect UV data
        uvData = []
        hasUVData = False
        if meshUV_textures.active:
            hasUVData = True
            for layer in meshUV_textures:
                faceIdxToUVdata = {}
                for fidx, uvface in enumerate(layer.data):
                    faceIdxToUVdata[fidx] = uvface.uv
                uvData.append(faceIdxToUVdata)

        # Vertex colour data
        colourData = {}
        alphaData = {}
        hasColourData = False
        if exportColour and meshVertex_colors.active:
            hasColourData = True
            # select colour and alpha layers
            colourLayer = meshVertex_colors.active
            alphaLayer = None
            for layer in meshVertex_colors:
                if layer.name == 'Alpha' or layer.name == 'alpha':
                    alphaLayer = layer

            # In case alpha layer is active
            if colourLayer == alphaLayer:
                colourLayer = None
                for layer in meshVertex_colors:
                    if layer != alphaLayer:
                        colourLayer = layer
                        break

            if colourLayer:
                for fidx, col in enumerate(colourLayer.data):
                    colourData[fidx] = [col.color1, col.color2, col.color3]

            # Alpha data
            if alphaLayer:
                for fidx, col in enumerate(alphaLayer.data):
                    alphaData[fidx] = [luminosity(col.color1),
                                       luminosity(col.color2),
                                       luminosity(col.color3)]

        map = {}

        import sys
        progressScale = 1.0 / (len(meshFaces) - 1)

        for fidx, F in enumerate(meshFaces):
            smooth = F.use_smooth
            faces = _sm_faces_[F.material_index]
            # Ogre only supports triangles
            tris = []
            tris.append((F.vertices[0], F.vertices[1], F.vertices[2]))

            if len(F.vertices) >= 4:
                tris.append((F.vertices[0], F.vertices[2], F.vertices[3]))

            # Progress
            percent = fidx * progressScale
            sys.stdout.write("\rVertices [" + '=' * int(percent*50) + '>' +
                             '.' * int(50-percent*50) + "] " +
                             str(int(percent*10000)/100.0) + "%   ")
            sys.stdout.flush()

            for tidx, tri in enumerate(tris):
                newFaceVx = []
                for vidx, idx in enumerate(tri):
                    vxOb = mesh.vertices[idx]
                    u = 0
                    v = 0
                    if hasUVData:
                        # take 1st layer only
                        uv = uvData[0][fidx][list(tri).index(idx)]
                        u = uv[0]
                        v = uv[1]

                    if smooth:
                        nx = vxOb.normal[0]
                        ny = vxOb.normal[1]
                        nz = vxOb.normal[2]
                    else:
                        nx = F.normal[0]
                        ny = F.normal[1]
                        nz = F.normal[2]

                    r = 1
                    g = 1
                    b = 1
                    a = 1
                    if hasColourData:
                        vi = list(tri).index(idx)
                        if colourData:
                            r, g, b = colourData[fidx][vi]
                        if alphaData:
                            a = alphaData[fidx][vi]

                    px = vxOb.co[0]
                    py = vxOb.co[1]
                    pz = vxOb.co[2]

                    # vertex groups
                    boneWeights = {}
                    for vxGroup in vxOb.groups:
                        if vxGroup.weight > 0.01:
                            vg = ob.vertex_groups[vxGroup.group]
                            boneWeights[vg.name] = vxGroup.weight

                    vert = VertexInfo(px, py, pz,
                                      nx, ny, nz,
                                      u, v,
                                      r, g, b, a,
                                      boneWeights, idx)

                    # newVxIdx = getVertexIndex(vert, _sm_verts_[F.material_index])
                    newVxIdx = map.get(vert)
                    if newVxIdx == None:
                        newVxIdx = len(_sm_verts_[F.material_index])
                        _sm_verts_[F.material_index].append(vert)
                        map[vert] = newVxIdx
                    newFaceVx.append(newVxIdx)

                faces.append(newFaceVx)
    print('')  # end progress line

    meshData['submeshes'] = []
    for matidx, mat in enumerate(materials):
        normals = []
        positions = []
        uvTex = []
        colours = []
        boneAssignments = []

        # vertex groups of object
        for vxInfo in _sm_verts_[matidx]:
            positions.append([vxInfo.px, vxInfo.py, vxInfo.pz])
            normals.append([vxInfo.nx, vxInfo.ny, vxInfo.nz])
            uvTex.append([[vxInfo.u, vxInfo.v]])
            colours.append([vxInfo.r, vxInfo.g, vxInfo.b, vxInfo.a])

            boneWeights = []
            for boneW in vxInfo.boneWeights.keys():
                boneWeights.append([boneW, vxInfo.boneWeights[boneW]])
            boneAssignments.append(boneWeights)

        # Shape keys - poses
        poses = None
        if exportPoses and mesh.shape_keys and mesh.shape_keys.key_blocks:
            poses = {}
            for pose in mesh.shape_keys.key_blocks:
                if pose.relative_key:
                    poseData = []
                    for index, v in enumerate(_sm_verts_[matidx]):
                        base = pose.relative_key.data[v.original].co
                        pos = pose.data[v.original].co
                        x = pos[0] - base[0]
                        y = pos[1] - base[1]
                        z = pos[2] - base[2]
                        if x != 0 or y != 0 or z != 0:
                            poseData.append((index, x, y, z))
                    if poseData:
                        poses[pose.name] = poseData

        subMeshData = {}
        subMeshData['geometry'] = {}
        subMeshData['geometry']['positions'] = positions
        subMeshData['geometry']['normals'] = normals
        subMeshData['geometry']['texcoordsets'] = len(mesh.uv_textures)

        if hasUVData:
            subMeshData['geometry']['uvsets'] = uvTex
        if hasColourData:
            subMeshData['geometry']['colours'] = colours

        # need bone name to bone ID dict
        subMeshData['geometry']['boneassignments'] = boneAssignments

        subMeshData['material'] = mat.name
        subMeshData['faces'] = _sm_faces_[matidx]
        subMeshData['geometry']['poses'] = poses
        if poses:
            subMeshData['geometry']['has_poses'] = True
        meshData['submeshes'].append(subMeshData)

    return meshData


def bCollectMeshDataOriginal(meshData, selectedObjects, applyModifiers,
                             exportColour, exportPoses):
    subMeshesData = []
    for ob in selectedObjects:
        subMeshData = {}
        # ob = bpy.types.Object ##
        materialName = ob.name
        if len(ob.data.materials) > 0:
            materialName = ob.data.materials[0].name
        # mesh = bpy.types.Mesh ##
        if applyModifiers:
            mesh = ob.to_mesh(bpy.context.scene, True, 'PREVIEW')
        else:
            mesh = ob.data

        # blender 2.62 <-> 2.63 compatibility
        if(blender_version <= 262):
            meshFaces = mesh.faces
            meshUV_textures = mesh.uv_textures
            meshVertex_colors = mesh.vertex_colors
        elif(blender_version > 262):
            mesh.update(calc_tessface=True)
            meshFaces = mesh.tessfaces
            meshUV_textures = mesh.tessface_uv_textures
            meshVertex_colors = mesh.tessface_vertex_colors

        # first try to collect UV data
        uvData = []
        hasUVData = False
        if meshUV_textures.active:
            hasUVData = True
            for layer in meshUV_textures:
                faceIdxToUVdata = {}
                for fidx, uvface in enumerate(layer.data):
                    faceIdxToUVdata[fidx] = uvface.uv
                uvData.append(faceIdxToUVdata)

        # Vertex colour data
        colourData = {}
        alphaData = {}
        hasColourData = False
        if exportColour and meshVertex_colors.active:
            hasColourData = True
            # select colour and alpha layers
            colourLayer = meshVertex_colors.active
            alphaLayer = None
            for layer in meshVertex_colors:
                if layer.name == 'Alpha' or layer.name == 'alpha':
                    alphaLayer = layer

            # In case alpha layer is active
            if colourLayer == alphaLayer:
                colourLayer = None
                for layer in meshVertex_colors:
                    if layer != alphaLayer:
                        colourLayer = layer
                        break

            if colourLayer:
                for fidx, col in enumerate(colourLayer.data):
                    colourData[fidx] = [col.color1, col.color2, col.color3]

            # Alpha data
            if alphaLayer:
                for fidx, col in enumerate(alphaLayer.data):
                    alphaData[fidx] = [luminosity(col.color1),
                                       luminosity(col.color2),
                                       luminosity(col.color3)]

        vertexList = []
        newFaces = []

        map = {}

        import sys
        progressScale = 1.0 / (len(meshFaces) - 1)

        for fidx, face in enumerate(meshFaces):
            tris = []
            tris.append((face.vertices[0], face.vertices[1], face.vertices[2]))
            if(len(face.vertices) >= 4):
                tris.append((face.vertices[0],
                             face.vertices[2],
                             face.vertices[3]))
            if SHOW_EXPORT_TRACE_VX:
                print("_face: " + str(fidx) + " indices [" +
                      str(list(face.vertices)) + "]")

            # Progress
            percent = fidx * progressScale
            sys.stdout.write("\rVertices [" + '=' * int(percent*50) + '>' +
                             '.' * int(50-percent*50) + "] " +
                             str(int(percent*10000)/100.0) + "%   ")
            sys.stdout.flush()

            for tri in tris:
                newFaceVx = []
                for vertex in tri:
                    vxOb = mesh.vertices[vertex]
                    u = 0
                    v = 0
                    if hasUVData:
                        uv = uvData[0][fidx][list(tri).index(vertex)]  # take 1st layer only
                        u = uv[0]
                        v = uv[1]

                    r = 1
                    g = 1
                    b = 1
                    a = 1
                    if hasColourData:
                        vi = list(tri).index(vertex)
                        if colourData:
                            r, g, b = colourData[fidx][vi]
                        if alphaData:
                            a = alphaData[fidx][vi]

                    px = vxOb.co[0]
                    py = vxOb.co[1]
                    pz = vxOb.co[2]
                    nx = vxOb.normal[0]
                    ny = vxOb.normal[1]
                    nz = vxOb.normal[2]

                    # vertex groups
                    boneWeights = {}
                    for vxGroup in vxOb.groups:
                        if vxGroup.weight > 0.01:
                            vg = ob.vertex_groups[vxGroup.group]
                            boneWeights[vg.name] = vxGroup.weight

                    if SHOW_EXPORT_TRACE_VX:
                        print("_vx: " + str(vertex) +
                              " co: " + str([px, py, pz]) +
                              " no: " + str([nx, ny, nz]) +
                              " uv: " + str([u, v]) +
                              " co: " + str([r, g, b]))

                    vert = VertexInfo(px, py, pz,
                                      nx, ny, nz,
                                      u, v,
                                      r, g, b, a,
                                      boneWeights,
                                      vertex)

                    # newVxIdx = getVertexIndex(vert, vertexList)
                    newVxIdx = map.get(vert)
                    if newVxIdx is None:
                        newVxIdx = len(vertexList)
                        vertexList.append(vert)
                        map[vert] = newVxIdx
                    newFaceVx.append(newVxIdx)

                    if SHOW_EXPORT_TRACE_VX:
                        print("Nvx: " + str(newVxIdx) +
                              " co: " + str([px, py, pz]) +
                              " no: " + str([nx, ny, nz]) +
                              " uv: " + str([u, v]))

                newFaces.append(newFaceVx)
                if SHOW_EXPORT_TRACE_VX:
                    print("Nface: " + str(fidx) +
                          " indices [" + str(list(newFaceVx)) + "]")

        print('')  # end progress line
        # geometry
        geometry = {}
        # vertices = bpy.types.MeshVertices
        # vertices = mesh.vertices
        faces = []
        normals = []
        positions = []
        uvTex = []
        colours = []
        # vertex groups of object
        boneAssignments = []

        faces = newFaces

        for vxInfo in vertexList:
            positions.append([vxInfo.px, vxInfo.py, vxInfo.pz])
            normals.append([vxInfo.nx, vxInfo.ny, vxInfo.nz])
            uvTex.append([[vxInfo.u, vxInfo.v]])
            colours.append([vxInfo.r, vxInfo.g, vxInfo.b, vxInfo.a])

            boneWeights = []
            for boneW in vxInfo.boneWeights.keys():
                boneWeights.append([boneW, vxInfo.boneWeights[boneW]])
            boneAssignments.append(boneWeights)
            # print(boneWeights)

        if SHOW_EXPORT_TRACE_VX:
            print("uvTex:")
            print(uvTex)
            print("boneAssignments:")
            print(boneAssignments)

        # Shape keys - poses
        poses = None
        if exportPoses and mesh.shape_keys and mesh.shape_keys.key_blocks:
            poses = {}
            for pose in mesh.shape_keys.key_blocks:
                if pose.relative_key:
                    poseData = []
                    for index, v in enumerate(vertexList):
                        base = pose.relative_key.data[v.original].co
                        pos = pose.data[v.original].co
                        x = pos[0] - base[0]
                        y = pos[1] - base[1]
                        z = pos[2] - base[2]
                        if x != 0 or y != 0 or z != 0:
                            poseData.append((index, x, y, z))
                    if poseData:
                        poses[pose.name] = poseData

        geometry['positions'] = positions
        geometry['normals'] = normals
        geometry['texcoordsets'] = len(mesh.uv_textures)
        if SHOW_EXPORT_TRACE:
            print("texcoordsets: " + str(len(mesh.uv_textures)))
        if hasUVData:
            geometry['uvsets'] = uvTex
        if hasColourData:
            geometry['colours'] = colours

        # need bone name to bone ID dict
        geometry['boneassignments'] = boneAssignments

        subMeshData['material'] = materialName
        subMeshData['faces'] = faces
        subMeshData['geometry'] = geometry
        subMeshData['poses'] = poses

        subMeshesData.append(subMeshData)

        if poses:
            meshData['has_poses'] = True

        # if mesh was newly created with modifiers, remove the mesh
        if applyModifiers:
            bpy.data.meshes.remove(mesh)

    meshData['submeshes'] = subMeshesData

    return meshData


def bCollectSkeletonData(blenderMeshData, selectedObjects):
    if SHOW_EXPORT_TRACE:
        print("bpy.data.armatures = %s" % bpy.data.armatures)

    # TODO: for now just take armature of first selected object
    if selectedObjects[0].find_armature():
        # creates and parses blender skeleton
        skeleton = Skeleton(selectedObjects[0])

        blenderMeshData['skeleton'] = skeleton


def bCollectMaterialData(blenderMeshData, selectedObjects):
    allMaterials = {}
    blenderMeshData['materials'] = allMaterials

    for ob in selectedObjects:
        if ob.type == 'MESH' and len(ob.data.materials) > 0:
            for mat in ob.data.materials:
                # mat = bpy.types.Material ##
                if mat.name not in allMaterials:
                    matInfo = {}
                    allMaterials[mat.name] = matInfo
                    # ambient
                    matInfo['ambient'] = [mat.ambient,
                                          mat.ambient,
                                          mat.ambient]
                    # diffuse
                    matInfo['diffuse'] = [mat.diffuse_color[0],
                                          mat.diffuse_color[1],
                                          mat.diffuse_color[2]]
                    # specular
                    matInfo['specular'] = [mat.specular_color[0],
                                           mat.specular_color[1],
                                           mat.specular_color[2]]
                    # emissive
                    matInfo['emissive'] = [mat.emit, mat.emit, mat.emit]
                    # texture
                    if len(mat.texture_slots) > 0:
                        if mat.texture_slots[0].texture:
                            matInfo['textures'] = []
                            for s in mat.texture_slots:
                                if s and s.texture.type == 'IMAGE' and s.texture.image:
                                    texInfo = {}
                                    texInfo['texture'] = s.texture.image.name
                                    texInfo['texture_path'] = s.texture.image.filepath
                                    matInfo['textures'].append(texInfo)


def calculateTangents(faces, positions, normals, uvs):
    tangents = [[0, 0, 0]] * len(positions)
    for face in faces:
        pa = positions[face[0]]
        pb = positions[face[1]]
        pc = positions[face[2]]
        ab = [pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]]
        ac = [pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]]

        # project ab, ac onto normal
        n = normals[face[0]]
        abn = ab[0] * n[0] + ab[1] * n[1] + ab[2] * n[2]
        acn = ac[0] * n[0] + ac[1] * n[1] + ac[2] * n[2]
        ab[0] -= n[0] * abn
        ab[1] -= n[1] * abn
        ab[2] -= n[2] * abn
        ac[0] -= n[0] * acn
        ac[1] -= n[1] * acn
        ac[2] -= n[2] * acn

        # texture coordinate deltas
        uva = uvs[face[0]][0]
        uvb = uvs[face[1]][0]
        uvc = uvs[face[2]][0]
        abu = uvb[0] - uva[0]
        abv = uvb[1] - uva[1]
        acu = uvc[0] - uva[0]
        acv = uvc[1] - uva[1]
        if acv*abu > abv*acu:
            acv = -acv
            abv = -abv

        # tangent
        tx = ac[0] * abv - ab[0] * acv
        ty = ac[1] * abv - ab[1] * acv
        tz = ac[2] * abv - ab[2] * acv

        # Normalise
        l = math.sqrt(tx*tx + ty*ty + tz * tz)
        if l != 0:
            tx = tx / l
            ty = ty / l
            tz = tz / l

        tangents[face[0]] = [tx, ty, tz]
        tangents[face[1]] = [tx, ty, tz]
        tangents[face[2]] = [tx, ty, tz]

    return tangents


def XMLtoOGREConvert(blenderMeshData, filepath, ogreXMLconverter,
                     export_skeleton, keep_xml):

    if ogreXMLconverter is None:
        return False

    # for mesh
    # use Ogre XML converter  xml -> binary mesh
    try:
        xmlFilepath = filepath + ".xml"
        subprocess.call([ogreXMLconverter, xmlFilepath])
        # remove XML file if successfully converted
        if keep_xml is False and os.path.isfile(filepath):
            os.unlink("%s" % xmlFilepath)

        if 'skeleton' in blenderMeshData and export_skeleton:
            # for skeleton
            skelFile = os.path.splitext(filepath)[0]  # removing .mesh
            xmlFilepath = skelFile + ".skeleton.xml"
            subprocess.call([ogreXMLconverter, xmlFilepath])
            # remove XML file
            if keep_xml is False:
                os.unlink("%s" % xmlFilepath)

        return True

    except:
        print("Error: Could not run", ogreXMLconverter)
        return False


def save(operator, context, filepath,
         xml_converter=None,
         keep_xml=False,
         export_tangents=False,
         export_binormals=False,
         export_colour=False,
         tangent_parity=False,
         apply_transform=True,
         apply_modifiers=True,
         overwrite_material=False,
         copy_textures=False,
         export_skeleton=False,
         enable_by_material=False,
         export_poses=False,
         export_animation=False,
         ):

    global blender_version

    blender_version = bpy.app.version[0]*100 + bpy.app.version[1]

    # just check if there is extension - .mesh
    if '.mesh' not in filepath.lower():
        filepath = filepath + ".mesh"

    print("saving...")
    print(str(filepath))

    # get mesh data from selected objects
    selectedObjects = []
    scn = bpy.context.scene
    for ob in scn.objects:
        if ob.select is True and ob.type != 'ARMATURE':
            selectedObjects.append(ob)

    if len(selectedObjects) == 0:
        print("No objects selected for export.")
        operator.report( {'WARNING'}, "No objects selected for export")
        return ('CANCELLED')

    # go to the object mode
    for ob in bpy.data.objects:
        bpy.ops.object.mode_set(mode='OBJECT')

    # apply transform
    if apply_transform:
        bpy.ops.object.transform_apply(rotation=True, scale=True)

    # Save Mesh
    blenderMeshData = {}

    # skeleton
    bCollectSkeletonData(blenderMeshData, selectedObjects)
    # mesh
    if enable_by_material:
        bCollectMeshData(blenderMeshData, selectedObjects, apply_modifiers, export_colour, export_poses)
    else:
        bCollectMeshDataOriginal(blenderMeshData, selectedObjects, apply_modifiers, export_colour, export_poses)
    # materials
    bCollectMaterialData(blenderMeshData, selectedObjects)

    # Calculate tangents
    if export_tangents:
        submeshes = blenderMeshData['submeshes']
        for mesh in submeshes:
            if SHOW_EXPORT_TRACE:
                for key in mesh.keys():
                    print(key)

            if 'uvsets' not in mesh['geometry']:
                operator.report({'WARNING'}, "Cannot export tangents with no UV maps.")
                break

            faces = mesh['faces']
            geometry = mesh['geometry']
            positions = geometry['positions']
            normals = geometry['normals']
            uvs = geometry['uvsets']

            tangents = calculateTangents(faces, positions, normals, uvs)
            geometry['tangents'] = tangents

            # Binormals
            if export_binormals:
                binormals = []
                for i in range(len(positions)):
                    bx = normals[i][1] * tangents[i][2] - normals[i][2] * tangents[i][1]
                    by = normals[i][2] * tangents[i][0] - normals[i][0] * tangents[i][2]
                    bz = normals[i][0] * tangents[i][1] - normals[i][1] * tangents[i][0]
                    binormals.append([bx, by, bz])
                geometry['binormals'] = binormals

    if export_animation:
        bCollectAnimationData(blenderMeshData)

    if SHOW_EXPORT_TRACE:
        print(blenderMeshData['materials'])

    if SHOW_EXPORT_DUMPS:
        dumpFile = filepath + ".EDump"
        fileWr = open(dumpFile, 'w')
        fileWr.write(str(blenderMeshData))
        fileWr.close()

    if export_skeleton:
        xSaveSkeletonData(blenderMeshData, filepath)

    xSaveMeshData(blenderMeshData, filepath, export_skeleton)

    xSaveMaterialData(filepath, blenderMeshData, overwrite_material, copy_textures)

    if not XMLtoOGREConvert(blenderMeshData, filepath, xml_converter, export_skeleton, keep_xml):
        operator.report({'WARNING'}, "Failed to convert .xml files to .mesh")

    print("done.")

    return {'FINISHED'}
