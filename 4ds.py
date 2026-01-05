from datetime import datetime
import os
import bpy # type: ignore
import bmesh # type: ignore
import struct
from mathutils import Quaternion, Matrix, Vector # type: ignore
from bpy_extras.io_utils import ImportHelper, ExportHelper # type: ignore
from bpy.props import StringProperty, EnumProperty, IntProperty, FloatProperty, FloatVectorProperty, BoolProperty # type: ignore
bl_info = {
    "name": "LS3D 4DS Importer/Exporter",
    "author": "Sev3n, Grok 3 (xAI)",
    "version": (1, 1),
    "blender": (5, 0, 1),
    "location": "File > Import/Export > 4DS Model File",
    "description": "Import and export LS3D .4ds files (Mafia)",
    "category": "Import-Export",
}
# FileVersion consts
VERSION_MAFIA = 29
VERSION_HD2 = 41
VERSION_CHAMELEON = 42
# FrameType consts
FRAME_VISUAL = 1
FRAME_LIGHT = 2
FRAME_CAMERA = 3
FRAME_SOUND = 4
FRAME_SECTOR = 5
FRAME_DUMMY = 6
FRAME_TARGET = 7
FRAME_USER = 8
FRAME_MODEL = 9
FRAME_JOINT = 10
FRAME_VOLUME = 11
FRAME_OCCLUDER = 12
FRAME_SCENE = 13
FRAME_AREA = 14
FRAME_LANDSCAPE = 15
# VisualType consts
VISUAL_OBJECT = 0
VISUAL_LITOBJECT = 1
VISUAL_SINGLEMESH = 2
VISUAL_SINGLEMORPH = 3
VISUAL_BILLBOARD = 4
VISUAL_MORPH = 5
VISUAL_LENS = 6
VISUAL_PROJECTOR = 7
VISUAL_MIRROR = 8
VISUAL_EMITOR = 9
VISUAL_SHADOW = 10
VISUAL_LANDPATCH = 11
# Material flags
MTL_DIFFUSETEX = 0x00040000
MTL_COLORED = 0x08000000
MTL_MIPMAP = 0x00800000
MTL_ANIMTEXDIFF = 0x04000000
MTL_ANIMTEXALPHA = 0x02000000
MTL_DOUBLESIDED = 0x10000000
MTL_ENVMAP = 0x00080000
MTL_NORMTEXBLEND = 0x00000100
MTL_MULTIPLYTEXBLEND = 0x00000200
MTL_ADDTEXBLEND = 0x00000400
MTL_CALCREFLECTTEXY = 0x00001000
MTL_PROJECTREFLECTTEXY = 0x00002000
MTL_PROJECTREFLECTTEXZ = 0x00004000
MTL_ADDEFFECT = 0x00008000
MTL_ALPHATEX = 0x40000000
MTL_COLORKEY = 0x20000000
MTL_ADDITIVEMIX = 0x80000000
MTL_UNLIT = 0x00000001
class The4DSPanel(bpy.types.Panel):
    bl_label = "4DS Properties"
    bl_idname = "OBJECT_PT_4ds"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    
    def draw(self, context):
        obj = context.object
        layout = self.layout
        
        if obj:
            if obj.type == 'MESH':
                layout.prop(obj, "visual_type", text="Mesh Type")
            
            layout.separator()
            
            # --- MAIN FLAGS ---
            box = layout.box()
            box.label(text="4ds Object Parameters", icon='PREFERENCES')
            
            if obj.type == 'MESH':
                # Render Flags 1
                box.prop(obj, "render_flags", text="Render Flags")
                
                # Render Flags 2
                split = box.split(factor=0.5)
                split.prop(obj, "render_flags2", text="Render Flags 2")
                
                col = split.column(align=True)
                r = col.row(); r.prop(obj, "rf2_depth_bias"); r.prop(obj, "rf2_shadowed")
                r = col.row(); r.prop(obj, "rf2_tex_proj"); r.prop(obj, "rf2_no_fog")
            
            # Cull Flags
            split = box.split(factor=0.5)
            split.prop(obj, "cull_flags", text="Culling Flags")
            
            cull_col = split.column(align=True)
            r = cull_col.row(); r.prop(obj, "cf_enabled"); r.prop(obj, "cf_unknown2"); r.prop(obj, "cf_unknown3"); r.prop(obj, "cf_unknown4")
            r = cull_col.row(); r.prop(obj, "cf_unknown5"); r.prop(obj, "cf_unknown6"); r.prop(obj, "cf_unknown7"); r.prop(obj, "cf_unknown8")
            
            # String Params
            box.prop(obj, "ls3d_user_props", text="String Params")
            
            layout.separator()
            
            # --- EXTRA PARAMETERS ---
            
            # LOD
            if obj.type == 'MESH':
                box = layout.box()
                box.prop(obj, "ls3d_lod_dist")
            
            # Portal
            if "plane" in obj.name.lower() or "portal" in obj.name.lower():
                box = layout.box()
                box.label(text="Portal", icon='OUTLINER_OB_LIGHT')
                box.prop(obj, "ls3d_portal_enabled")
                box.prop(obj, "ls3d_portal_flags")
                row = box.row()
                row.prop(obj, "ls3d_portal_near")
                row.prop(obj, "ls3d_portal_far")
                box.prop(obj, "ls3d_portal_unknown")

            # Sector
            if obj.type == 'MESH' and "sector" in obj.name.lower():
                box = layout.box()
                box.label(text="Sector", icon='SCENE_DATA')
                box.prop(obj, "ls3d_sector_flags1")
                box.prop(obj, "ls3d_sector_flags2")

            # Billboard
            if obj.type == 'MESH' and obj.visual_type == '4':
                box = layout.box()
                box.label(text="Billboard", icon='IMAGE_PLANE')
                box.prop(obj, "rot_mode")
                box.prop(obj, "rot_axis")

            # Mirror
            if obj.type == 'MESH' and obj.visual_type == '8':
                box = layout.box()
                box.label(text="Mirror", icon='MOD_MIRROR')
                box.prop(obj, "mirror_color")
                box.prop(obj, "mirror_dist")

            layout.separator()
            if obj.type == 'MESH':
                layout.label(text="LS3D Material Tools:")
                layout.operator("node.add_ls3d_group", icon='NODE')
                
def safe_link(tree, from_socket, to_socket):
    if from_socket and to_socket:
        tree.links.new(from_socket, to_socket)

def get_or_create_ls3d_group():
    group_name = "LS3D Material Data"
    
    # 1. Get or Create Group
    if group_name in bpy.data.node_groups:
        ng = bpy.data.node_groups[group_name]
        # Check if we need to update the internal logic (if Mix Shader is missing)
        has_mix = any(n.type == 'MIX_SHADER' for n in ng.nodes)
        if not has_mix:
            ng.nodes.clear() # Rebuild old versions
    else:
        ng = bpy.data.node_groups.new(name=group_name, type='ShaderNodeTree')

    # 2. Create Interface (Sockets)
    # Use check to prevent duplicate sockets on re-run
    if not ng.interface.items_tree:
        ng.interface.new_socket("Environment Color", in_out='INPUT', socket_type='NodeSocketColor')
        ng.interface.new_socket("Diffuse Color", in_out='INPUT', socket_type='NodeSocketColor')
        ng.interface.new_socket("Emission Color", in_out='INPUT', socket_type='NodeSocketColor')
        ng.interface.new_socket("Color Key Value", in_out='INPUT', socket_type='NodeSocketColor')
        
        ng.interface.new_socket("Opacity", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("Env Intensity", in_out='INPUT', socket_type='NodeSocketFloat')
        
        ng.interface.new_socket("F: Double Sided", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("F: Colored", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("F: Unlit", in_out='INPUT', socket_type='NodeSocketFloat') # The Socket
        ng.interface.new_socket("F: Color Key", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("F: Add Effect (Alpha)", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("F: Env Map", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("F: Disable Z-Write", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("F: Mip Map", in_out='INPUT', socket_type='NodeSocketFloat')

        ng.interface.new_socket("BSDF", in_out='OUTPUT', socket_type='NodeSocketShader')

    # Ensure sockets exist if group existed but was old
    if "F: Unlit" not in ng.interface.items_tree:
         ng.interface.new_socket("F: Unlit", in_out='INPUT', socket_type='NodeSocketFloat')

    # 3. Create Nodes
    # If nodes exist, we skip creation to preserve existing layout, 
    # unless we cleared it above because it was outdated.
    if not ng.nodes:
        input_node = ng.nodes.new('NodeGroupInput')
        input_node.location = (-800, 0)
        output_node = ng.nodes.new('NodeGroupOutput')
        output_node.location = (800, 0)
        
        # Lit Shader
        principled = ng.nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (300, 100)
        
        # Unlit Shader (Emission)
        emission = ng.nodes.new('ShaderNodeEmission')
        emission.location = (300, -150)
        emission.label = "Unlit (Shadeless)"
        
        # Switcher
        mix_shader = ng.nodes.new('ShaderNodeMixShader')
        mix_shader.location = (600, 0)
        mix_shader.label = "Lit/Unlit Switch"
        
        # Alpha/Color Key Logic
        dist_node = ng.nodes.new('ShaderNodeVectorMath')
        dist_node.operation = 'DISTANCE'
        dist_node.location = (-400, -200)
        
        is_match = ng.nodes.new('ShaderNodeMath')
        is_match.operation = 'LESS_THAN'
        is_match.inputs[1].default_value = 0.005 
        is_match.location = (-200, -200)
        
        flag_check = ng.nodes.new('ShaderNodeMath')
        flag_check.operation = 'MULTIPLY'
        flag_check.location = (-50, -200)
        
        invert_mask = ng.nodes.new('ShaderNodeMath')
        invert_mask.operation = 'SUBTRACT'
        invert_mask.inputs[0].default_value = 1.0
        invert_mask.location = (100, -200)
        
        final_alpha = ng.nodes.new('ShaderNodeMath')
        final_alpha.operation = 'MULTIPLY'
        final_alpha.location = (100, -350)
        
        # Defaults
        for socket in ng.interface.items_tree:
            if socket.bl_socket_idname == 'NodeSocketColor':
                if "Environment" in socket.name: socket.default_value = (0.5, 0.5, 0.5, 1.0)
                elif "Color Key" in socket.name: socket.default_value = (1.0, 0.0, 1.0, 1.0) 
                else: socket.default_value = (1.0, 1.0, 1.0, 1.0)
            elif socket.bl_socket_idname == 'NodeSocketFloat':
                if "Opacity" in socket.name: socket.default_value = 1.0
                else: socket.default_value = 0.0
                if "F:" in socket.name: socket.min_value = 0.0; socket.max_value = 1.0

        # Links
        inputs = input_node.outputs
        
        # Connect to Lit
        safe_link(ng, inputs.get("Diffuse Color"), principled.inputs["Base Color"])
        safe_link(ng, inputs.get("Emission Color"), principled.inputs["Emission Color"])
        safe_link(ng, inputs.get("Env Intensity"), principled.inputs["Metallic"])
        
        # Connect to Unlit (Use Diffuse as Emission Color)
        safe_link(ng, inputs.get("Diffuse Color"), emission.inputs["Color"])
        
        # Alpha Logic
        safe_link(ng, inputs.get("Diffuse Color"), dist_node.inputs[0])
        safe_link(ng, inputs.get("Color Key Value"), dist_node.inputs[1])
        safe_link(ng, dist_node.outputs[0], is_match.inputs[0])
        safe_link(ng, is_match.outputs[0], flag_check.inputs[0])
        safe_link(ng, inputs.get("F: Color Key"), flag_check.inputs[1])
        safe_link(ng, flag_check.outputs[0], invert_mask.inputs[1])
        safe_link(ng, invert_mask.outputs[0], final_alpha.inputs[0])
        safe_link(ng, inputs.get("Opacity"), final_alpha.inputs[1])
        
        # Connect Alpha to both
        safe_link(ng, final_alpha.outputs[0], principled.inputs["Alpha"])
        safe_link(ng, final_alpha.outputs[0], emission.inputs["Strength"]) 
        
        # Connect Switcher
        # If F: Unlit is 1, use Emission (Socket 2). If 0, use Principled (Socket 1)
        safe_link(ng, inputs.get("F: Unlit"), mix_shader.inputs["Fac"])
        safe_link(ng, principled.outputs["BSDF"], mix_shader.inputs[1])
        safe_link(ng, emission.outputs["Emission"], mix_shader.inputs[2])
        
        safe_link(ng, mix_shader.outputs["Shader"], output_node.inputs["BSDF"])
    
    return ng

class LS3D_OT_AddNode(bpy.types.Operator):
    """Add LS3D Material Data Node to the current material"""
    bl_idname = "node.add_ls3d_group"
    bl_label = "Add LS3D Node"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or not obj.active_material:
            self.report({'ERROR'}, "No active object or material found.")
            return {'CANCELLED'}
        mat = obj.active_material
        if not mat.use_nodes: mat.use_nodes = True
        tree = mat.node_tree
        group_data = get_or_create_ls3d_group()
        group_node = tree.nodes.new('ShaderNodeGroup')
        group_node.node_tree = group_data
        group_node.location = (-300, 200)
        group_node.width = 240
        for n in tree.nodes: n.select = False
        group_node.select = True
        tree.nodes.active = group_node
        return {'FINISHED'}
    
class LS3D_OT_AddNode(bpy.types.Operator):
    """Add LS3D Material Data Node to the current material"""
    bl_idname = "node.add_ls3d_group"
    bl_label = "Add LS3D Node"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or not obj.active_material:
            self.report({'ERROR'}, "No active object or material found.")
            return {'CANCELLED'}
            
        mat = obj.active_material
        if not mat.use_nodes:
            mat.use_nodes = True
            
        tree = mat.node_tree
        group_data = get_or_create_ls3d_group()
        
        # Create the Group Node
        group_node = tree.nodes.new('ShaderNodeGroup')
        group_node.node_tree = group_data
        group_node.location = (-300, 200)
        group_node.width = 240
        
        # Deselect all and select new node
        for n in tree.nodes:
            n.select = False
        group_node.select = True
        tree.nodes.active = group_node
        
        return {'FINISHED'}

class The4DSExporter:
    def __init__(self, filepath, objects):
        self.filepath = filepath
        self.objects_to_export = objects
        self.materials = []
        self.objects = []
        self.version = VERSION_MAFIA
        self.frames_map = {}
        self.joint_map = {}
        self.frame_index = 1
        self.lod_map = {}
    def write_string(self, f, string):
        encoded = string.encode("windows-1250")
        f.write(struct.pack("B", len(encoded)))
        if len(encoded) > 0:
            f.write(encoded)
    def serialize_header(self, f):
        f.write(b"4DS\0")
        f.write(struct.pack("<H", self.version))
        now = datetime.now()
        epoch = datetime(1601, 1, 1)
        delta = now - epoch
        filetime = int(delta.total_seconds() * 1e7)
        f.write(struct.pack("<Q", filetime))
    def collect_materials(self):
        materials = set()
        for obj in self.objects_to_export:
            if obj.type == 'MESH':
                for slot in obj.material_slots:
                    if slot.material:
                        materials.add(slot.material)
        return list(materials)
    def find_texture_node(self, node):
        """Recursively find an Image Texture node feeding into this node."""
        if not node:
            return None
        if node.type == 'TEX_IMAGE':
            return node
      
        # Pass through Mix/Add/Multiply nodes
        if node.type in {'MIX_RGB', 'MATH', 'MIX_SHADER', 'ADD_SHADER'}:
            # Check inputs. Usually input[1] or input[2] for MixRGB color slots.
            # We check all linked inputs for an image.
            for input_socket in node.inputs:
                if input_socket.is_linked:
                    found = self.find_texture_node(input_socket.links[0].from_node)
                    if found:
                        return found
        return None
    
    
                
    def serialize_singlemesh(self, f, obj, num_lods):
        armature_mod = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None)
        if not armature_mod or not armature_mod.object:
            return
        armature = armature_mod.object
        bones = list(armature.data.bones)
        total_verts = len(obj.data.vertices)
        for _ in range(num_lods):
            f.write(struct.pack("<B", len(bones)))
            # Unweighted verts count (assigned to root)
            weighted_verts = set()
            for v in obj.data.vertices:
                if any(g.weight > 0.0 for g in v.groups):
                    weighted_verts.add(v.index)
            unweighted_count = total_verts - len(weighted_verts)
            f.write(struct.pack("<I", unweighted_count))
            # Mesh bounds
            coords = [v.co for v in obj.data.vertices]
            min_b = Vector((min(c[i] for c in coords) for i in range(3)))
            max_b = Vector((max(c[i] for c in coords) for i in range(3)))
            f.write(struct.pack("<3f", min_b.x, min_b.z, min_b.y))
            f.write(struct.pack("<3f", max_b.x, max_b.z, max_b.y))
            for bone_idx, bone in enumerate(bones):
                # Inverse bind pose
                mat = bone.matrix_local.copy()
                # Y/Z swap for Mafia coord system
                mat = mat @ Matrix([[1,0,0,0], [0,0,1,0], [0,1,0,0], [0,0,0,1]])
                inv = mat.inverted()
                # Row-major flatten
                flat = [inv[i][j] for i in range(4) for j in range(4)]
                f.write(struct.pack("<16f", *flat))
                vg = obj.vertex_groups.get(bone.name)
                if not vg:
                    f.write(struct.pack("<4I", 0, 0, bone_idx, 0))
                    f.write(struct.pack("<6f", min_b.x, min_b.z, min_b.y, max_b.x, max_b.z, max_b.y))
                    continue
                locked = []
                weighted = []
                weights = []
                for v_idx in range(total_verts):
                    try:
                        weight = vg.weight(v_idx)
                    except RuntimeError:
                        continue
                    if weight >= 0.999:
                        locked.append(v_idx)
                    elif weight > 0.001:
                        weighted.append(v_idx)
                        weights.append(weight)
                f.write(struct.pack("<I", len(locked)))
                f.write(struct.pack("<I", len(weighted)))
                f.write(struct.pack("<I", bone_idx))
                f.write(struct.pack("<3f", min_b.x, min_b.z, min_b.y))
                f.write(struct.pack("<3f", max_b.x, max_b.z, max_b.y))
                for w in weights:
                    f.write(struct.pack("<f", w))
                    
    def serialize_morph(self, f, obj, num_lods):
        shape_keys = obj.data.shape_keys
        if not shape_keys or len(shape_keys.key_blocks) <= 1:
            f.write(struct.pack("<B", 0))
            return
        morph_data = {}
        for key in shape_keys.key_blocks[1:]:
            parts = key.name.split("_")
            if len(parts) >= 2 and parts[0] == "Target":
                try:
                    target_idx = int(parts[1])
                    lod_idx = 0
                    channel_idx = 0
                    for part in parts[2:]:
                        if part.startswith("LOD"):
                            lod_idx = int(part[3:])
                        elif part.startswith("Channel"):
                            channel_idx = int(part[7:])
                    if lod_idx < num_lods:
                        morph_data.setdefault(lod_idx, {}).setdefault(channel_idx, []).append((target_idx, key))
                except:
                    continue
        num_targets = max((len(targets) for lod in morph_data.values() for targets in lod.values()), default=1)
        num_channels = max((len(lod) for lod in morph_data.values()), default=1)
        f.write(struct.pack("<B", num_targets))
        f.write(struct.pack("<B", num_channels))
        f.write(struct.pack("<B", num_lods))
        for lod_idx in range(num_lods):
            for channel_idx in range(num_channels):
                targets = morph_data.get(lod_idx, {}).get(channel_idx, [])
                num_vertices = len(obj.data.vertices)
                f.write(struct.pack("<H", num_vertices))
                for vert_idx in range(num_vertices):
                    for target_idx in range(num_targets):
                        target_key = next((k for t, k in targets if t == target_idx), None)
                        pos = target_key.data[vert_idx].co if target_key else obj.data.vertices[vert_idx].co
                        norm = obj.data.vertices[vert_idx].normal
                        f.write(struct.pack("<3f", pos.x, pos.z, pos.y))
                        f.write(struct.pack("<3f", norm.x, norm.z, norm.y))
                f.write(struct.pack("<?", False))
            bounds = [v.co for v in obj.data.vertices]
            min_bounds = Vector((min(v.x for v in bounds), min(v.y for v in bounds), min(v.z for v in bounds)))
            max_bounds = Vector((max(v.x for v in bounds), max(v.y for v in bounds), max(v.z for v in bounds)))
            center = (min_bounds + max_bounds) / 2
            dist = (max_bounds - min_bounds).length
            f.write(struct.pack("<3f", min_bounds.x, min_bounds.z, min_bounds.y))
            f.write(struct.pack("<3f", max_bounds.x, max_bounds.z, max_bounds.y))
            f.write(struct.pack("<3f", center.x, center.z, center.y))
            f.write(struct.pack("<f", dist))
    def serialize_dummy(self, f, obj):
        min_bounds = obj.get("bbox_min", (0.0, 0.0, 0.0))
        max_bounds = obj.get("bbox_max", (0.0, 0.0, 0.0))
        f.write(struct.pack("<3f", min_bounds[0], min_bounds[2], min_bounds[1]))
        f.write(struct.pack("<3f", max_bounds[0], max_bounds[2], max_bounds[1]))
    def serialize_target(self, f, obj):
        f.write(struct.pack("<H", 0))
        link_ids = obj.get("link_ids", [])
        f.write(struct.pack("<B", len(link_ids)))
        if link_ids:
            f.write(struct.pack(f"<{len(link_ids)}H", *link_ids))

    def serialize_occluder(self, f, obj):
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        f.write(struct.pack("<I", len(bm.verts)))
        f.write(struct.pack("<I", len(bm.faces)))
        for vert in bm.verts:
            pos = vert.co
            f.write(struct.pack("<3f", pos.x, pos.z, pos.y))
        for face in bm.faces:
            idxs = [vert.index for vert in face.verts]
            f.write(struct.pack("<3H", idxs[0], idxs[2], idxs[1]))
        bm.free()
    def serialize_joint(self, f, bone, armature, parent_id):
        matrix = bone.matrix_local.copy()
        matrix[1], matrix[2] = matrix[2].copy(), matrix[1].copy()
        flat = [matrix[i][j] for i in range(4) for j in range(3)]
        f.write(struct.pack("<12f", *flat))
        bone_idx = list(armature.data.bones).index(bone)
        f.write(struct.pack("<I", bone_idx))
    
    def serialize_material(self, f, mat, mat_index):
        # 1. Try to find the LS3D Node Group
        nodes = mat.node_tree.nodes if mat.use_nodes else []
        ls3d_node = next((n for n in nodes if n.type == 'GROUP' and n.node_tree and "LS3D Material Data" in n.node_tree.name), None)
        
        flags = 0
        diffuse_tex = ""
        alpha_tex = ""
        env_tex = ""
        
        # Defaults (Fallback only)
        env_color = (0.5, 0.5, 0.5)
        diffuse_color = (1.0, 1.0, 1.0)
        emission_color = (0.0, 0.0, 0.0)
        opacity = 1.0
        env_opacity = 0.0

        if ls3d_node:
            inputs = ls3d_node.inputs
            # --- CRITICAL FIX: Read Colors exactly as imported ---
            # Do not multiply or modify these.
            env_color = inputs["Environment Color"].default_value[:3]
            diffuse_color = inputs["Diffuse Color"].default_value[:3]
            emission_color = inputs["Emission Color"].default_value[:3]
            opacity = inputs["Opacity"].default_value
            env_opacity = inputs["Env Intensity"].default_value
            
            # Read Flags
            if inputs["F: Double Sided"].default_value > 0.5: flags |= MTL_DOUBLESIDED
            if inputs["F: Colored"].default_value > 0.5: flags |= MTL_COLORED
            if inputs["F: Unlit"].default_value > 0.5: flags |= MTL_UNLIT
            if inputs["F: Color Key"].default_value > 0.5: flags |= MTL_COLORKEY
            if inputs["F: Add Effect (Alpha)"].default_value > 0.5: flags |= MTL_ADDEFFECT
            if inputs["F: Env Map"].default_value > 0.5: flags |= MTL_ENVMAP
            if inputs["F: Mip Map"].default_value > 0.5: flags |= MTL_MIPMAP
            if inputs["F: Disable Z-Write"].default_value > 0.5: flags |= MTL_ADDITIVEMIX 

            # Detect Textures
            if inputs["Diffuse Color"].is_linked:
                link = inputs["Diffuse Color"].links[0]
                tex = self.find_texture_node(link.from_node)
                if tex and tex.image:
                    diffuse_tex = os.path.basename(tex.image.filepath or tex.image.name).upper()
                    flags |= MTL_DIFFUSETEX 
            else:
                # If no texture is linked, we MUST set Colored flag so the Diffuse Color is used
                flags |= MTL_COLORED
            
            if inputs["Opacity"].is_linked:
                link = inputs["Opacity"].links[0]
                tex = self.find_texture_node(link.from_node)
                if tex and tex.image:
                    tname = os.path.basename(tex.image.filepath or tex.image.name).upper()
                    if tname != diffuse_tex:
                        alpha_tex = tname
                        flags |= MTL_ALPHATEX
        else:
            # Fallback for Materials created by user without the Addon Node
            flags |= MTL_COLORED
            if hasattr(mat, 'diffuse_color'):
                base = mat.diffuse_color[:3]
                diffuse_color = tuple(base)
                # Only here do we guess ambient
                env_color = (base[0] * 0.5, base[1] * 0.5, base[2] * 0.5)
            
        f.write(struct.pack("<I", flags))
        f.write(struct.pack("<3f", *env_color))
        f.write(struct.pack("<3f", *diffuse_color))
        f.write(struct.pack("<3f", *emission_color))
        f.write(struct.pack("<f", opacity))

        if flags & MTL_ENVMAP:
            f.write(struct.pack("<f", env_opacity))
            self.write_string(f, env_tex)

        self.write_string(f, diffuse_tex)

        if (flags & MTL_ADDEFFECT) and (flags & MTL_ALPHATEX):
            self.write_string(f, alpha_tex)

    def serialize_object(self, f, obj, lods):
        f.write(struct.pack("<H", 0))
        f.write(struct.pack("<B", len(lods)))
        
        for lod_idx, lod_obj in enumerate(lods):
            # 1. Get Mesh Data
            mesh = lod_obj.data
            
            # 2. Create BMesh to Triangulate
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.triangulate(bm, faces=bm.faces)
            
            # 3. Convert to Temp Mesh for Loop Normals
            # We cannot use BMesh directly for loop normals easily in export without calc
            temp_mesh = bpy.data.meshes.new("TempExportMesh")
            bm.to_mesh(temp_mesh)
            bm.free()
            
            # Ensure normals are calculated
            if not temp_mesh.has_custom_normals:
                temp_mesh.calc_normals()
            
            uv_layer = temp_mesh.uv_layers.active.data if temp_mesh.uv_layers.active else None
            
            unique_verts = {}
            final_verts = []
            mat_groups = {}
            
            # 4. Iterate POLYGONS (Not Faces) on Temp Mesh
            for poly in temp_mesh.polygons:
                f_indices = []
                for loop_index in poly.loop_indices:
                    loop = temp_mesh.loops[loop_index]
                    v_index = loop.vertex_index
                    v_co = temp_mesh.vertices[v_index].co
                    
                    # UV
                    u, v_coord = (0.0, 0.0)
                    if uv_layer:
                        uv_data = uv_layer[loop_index].uv
                        u, v_coord = uv_data[0], 1.0 - uv_data[1]
                    
                    # --- NORMAL FIX ---
                    # Use LOOP normal. This preserves Split Normals / Hard Edges.
                    # Previous code used v.normal which averaged them (causing the 0.94 value).
                    nx, ny, nz = loop.normal.x, loop.normal.y, loop.normal.z
                    
                    # Deduplication Key (Includes Normal)
                    key = (
                        round(v_co.x, 5), round(v_co.y, 5), round(v_co.z, 5),
                        round(nx, 5), round(ny, 5), round(nz, 5),
                        round(u, 5), round(v_coord, 5)
                    )
                    
                    if key in unique_verts:
                        idx = unique_verts[key]
                    else:
                        idx = len(final_verts)
                        unique_verts[key] = idx
                        # Swap Axis X, Z, Y for Mafia
                        final_verts.append({
                            'pos': (v_co.x, v_co.z, v_co.y),
                            'norm': (nx, nz, ny), 
                            'uv': (u, v_coord)
                        })
                    f_indices.append(idx)
                
                mat_groups.setdefault(poly.material_index, []).append(f_indices)
            
            # Clean up temp mesh
            bpy.data.meshes.remove(temp_mesh)
            
            # Write LOD Distance
            # If property exists, use it. If LOD 0, default to 0.0 (Matches original file).
            if hasattr(lod_obj, "ls3d_lod_dist"):
                dist = lod_obj.ls3d_lod_dist
            else:
                dist = 0.0 if lod_idx == 0 else 100.0 * lod_idx
            
            f.write(struct.pack("<f", dist))
            
            # Write Verts
            f.write(struct.pack("<H", len(final_verts)))
            for v in final_verts:
                f.write(struct.pack("<3f", *v['pos']))
                f.write(struct.pack("<3f", *v['norm']))
                f.write(struct.pack("<2f", *v['uv']))
            
            # Write Faces
            f.write(struct.pack("<B", len(mat_groups)))
            for mat_idx, faces in mat_groups.items():
                f.write(struct.pack("<H", len(faces)))
                for idxs in faces:
                    f.write(struct.pack("<3H", idxs[0], idxs[2], idxs[1]))
                
                real_mat = lod_obj.material_slots[mat_idx].material if mat_idx < len(lod_obj.material_slots) else None
                mat_id = self.materials.index(real_mat) + 1 if real_mat in self.materials else 0
                f.write(struct.pack("<H", mat_id))
            
        return len(lods)
                        
    def serialize_frame(self, f, obj):
        frame_type = FRAME_VISUAL
        visual_type = VISUAL_OBJECT
        
        # Read Render Flags from UI properties
        r_flag1 = getattr(obj, "render_flags", 128)
        r_flag2 = getattr(obj, "render_flags2", 42)
        visual_flags = (r_flag1, r_flag2)
        
        if obj.type == "MESH":
            if hasattr(obj, "visual_type"):
                visual_type = int(obj.visual_type)
                # Validation for Skinned Meshes
                if visual_type in (VISUAL_SINGLEMESH, VISUAL_SINGLEMORPH):
                    has_arm = any(m.type == 'ARMATURE' and m.object for m in obj.modifiers)
                    if not has_arm: visual_type = VISUAL_OBJECT
            else:
                # Auto-detect
                if obj.modifiers and any(mod.type == "ARMATURE" for mod in obj.modifiers):
                    visual_type = VISUAL_SINGLEMORPH if obj.data.shape_keys else VISUAL_SINGLEMESH
                elif "portal" in obj.name.lower(): pass # Skip (handled by sector)
                elif "sector" in obj.name.lower(): frame_type = FRAME_SECTOR
                elif obj.display_type == "WIRE": frame_type = FRAME_OCCLUDER
                elif obj.data.shape_keys: visual_type = VISUAL_MORPH
        
        elif obj.type == "EMPTY":
            if obj.empty_display_type == "CUBE": frame_type = FRAME_DUMMY
            elif obj.empty_display_type == "PLAIN_AXES": frame_type = FRAME_TARGET
        elif obj.type == "ARMATURE": return
            
        parent_id = self.frames_map.get(obj.parent, 0)
        matrix = obj.matrix_local if obj.parent else obj.matrix_world
        pos = matrix.to_translation()
        rot = matrix.to_quaternion()
        scale = matrix.to_scale()
        self.frames_map[obj] = self.frame_index
        self.frame_index += 1
        
        # --- HEADER ---
        f.write(struct.pack("<B", frame_type))
        
        if frame_type == FRAME_VISUAL:
            f.write(struct.pack("<B", visual_type))
            f.write(struct.pack("<2B", *visual_flags))
            
        f.write(struct.pack("<H", parent_id))
        f.write(struct.pack("<3f", pos.x, pos.z, pos.y))
        f.write(struct.pack("<3f", scale.x, scale.z, scale.y))
        f.write(struct.pack("<4f", rot.w, rot.x, rot.z, rot.y))
        
        # Cull Flags
        f.write(struct.pack("<B", getattr(obj, "cull_flags", 128)))
        
        # Strings
        self.write_string(f, obj.name)
        self.write_string(f, getattr(obj, "ls3d_user_props", ""))
        
        # --- BODY ---
        if frame_type == FRAME_VISUAL:
            lods = self.lod_map.get(obj, [obj])
            
            if visual_type in (VISUAL_OBJECT, VISUAL_LITOBJECT):
                self.serialize_object(f, obj, lods)
                
            elif visual_type == VISUAL_BILLBOARD:
                self.serialize_object(f, obj, lods)
                self.serialize_billboard(f, obj) # NEW
                
            elif visual_type == VISUAL_MIRROR:
                self.serialize_mirror(f, obj) # NEW
                
            elif visual_type == VISUAL_SINGLEMESH:
                num = self.serialize_object(f, obj, lods)
                self.serialize_singlemesh(f, obj, num)
            elif visual_type == VISUAL_SINGLEMORPH:
                num = self.serialize_object(f, obj, lods)
                self.serialize_singlemesh(f, obj, num)
                self.serialize_morph(f, obj, num)
            elif visual_type == VISUAL_MORPH:
                num = self.serialize_object(f, obj, lods)
                self.serialize_morph(f, obj, num)

        elif frame_type == FRAME_SECTOR:
            self.serialize_sector(f, obj)
        elif frame_type == FRAME_DUMMY:
            self.serialize_dummy(f, obj)
        elif frame_type == FRAME_TARGET:
            self.serialize_target(f, obj)
        elif frame_type == FRAME_OCCLUDER:
            self.serialize_occluder(f, obj)

    def serialize_billboard(self, f, obj):
        # Enum is '0','1','2' string. File needs 1-based index integer.
        # X=0(1), Z=1(2), Y=2(3)
        axis = int(getattr(obj, "rot_axis", '1')) + 1
        mode = int(getattr(obj, "rot_mode", '0')) + 1
        f.write(struct.pack("<I", axis))
        f.write(struct.pack("<B", mode))

    def serialize_mirror(self, f, obj):
        # Bounds
        min_b = getattr(obj, "bbox_min", (-1,-1,-1))
        max_b = getattr(obj, "bbox_max", (1,1,1))
        f.write(struct.pack("<3f", min_b[0], min_b[2], min_b[1]))
        f.write(struct.pack("<3f", max_b[0], max_b[2], max_b[1]))
        
        # Center/Radius
        f.write(struct.pack("<3f", 0,0,0)) 
        f.write(struct.pack("<f", 10.0))
        
        # Matrix (Identity)
        m = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]
        f.write(struct.pack("<16f", *m))
        
        # Color
        col = getattr(obj, "mirror_color", (0,0,0))
        f.write(struct.pack("<3f", *col))
        
        # Dist
        f.write(struct.pack("<f", getattr(obj, "mirror_dist", 100.0)))
        
        # Mesh
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        f.write(struct.pack("<I", len(bm.verts)))
        f.write(struct.pack("<I", len(bm.faces)))
        for v in bm.verts:
            f.write(struct.pack("<3f", v.co.x, v.co.z, v.co.y))
        for face in bm.faces:
            f.write(struct.pack("<3H", face.verts[0].index, face.verts[2].index, face.verts[1].index))
        bm.free()

    def serialize_sector(self, f, obj):
        # Flags
        f1 = getattr(obj, "ls3d_sector_flags1", 2049)
        f2 = getattr(obj, "ls3d_sector_flags2", 0)
        f.write(struct.pack("<2I", f1, f2))
        
        # Mesh
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        
        f.write(struct.pack("<I", len(bm.verts)))
        f.write(struct.pack("<I", len(bm.faces)))
        
        for vert in bm.verts:
            f.write(struct.pack("<3f", vert.co.x, vert.co.z, vert.co.y))
        for face in bm.faces:
            f.write(struct.pack("<3H", face.verts[0].index, face.verts[2].index, face.verts[1].index))
            
        # Bounds
        min_b = getattr(obj, "bbox_min", (0,0,0))
        max_b = getattr(obj, "bbox_max", (0,0,0))
        f.write(struct.pack("<3f", min_b[0], min_b[2], min_b[1]))
        f.write(struct.pack("<3f", max_b[0], max_b[2], max_b[1]))
        
        # Portals
        portals = [c for c in obj.children if "portal" in c.name.lower() or "plane" in c.name.lower()]
        f.write(struct.pack("<B", len(portals)))
        
        for p_obj in portals:
            self.serialize_portal(f, p_obj)
        
        bm.free()

    def serialize_portal(self, f, obj):
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        
        f.write(struct.pack("<B", len(bm.verts)))
        
        # Flags, Near, Far
        f.write(struct.pack("<I", getattr(obj, "ls3d_portal_flags", 4)))
        f.write(struct.pack("<f", getattr(obj, "ls3d_portal_near", 0.0)))
        f.write(struct.pack("<f", getattr(obj, "ls3d_portal_far", 100.0)))
        
        # Normal
        norm = obj.matrix_world.to_quaternion() @ Vector((0,0,1))
        f.write(struct.pack("<3f", norm.x, norm.z, norm.y))
        f.write(struct.pack("<f", 0.0)) # Dot
        
        for v in bm.verts:
            f.write(struct.pack("<3f", v.co.x, v.co.z, v.co.y))
            
        bm.free()
    
    def serialize_joints(self, f, armature):
        for bone in armature.data.bones:
            frame_type = FRAME_JOINT
            parent_id = self.joint_map.get(bone.parent.name, self.frames_map.get(armature, 0)) if bone.parent else 0
            # Calculate Relative Transform for Header
            if bone.parent:
                matrix = bone.parent.matrix_local.inverted() @ bone.matrix_local
            else:
                matrix = bone.matrix_local
            pos = matrix.to_translation()
            rot = matrix.to_quaternion()
            scale = matrix.to_scale()
            self.joint_map[bone.name] = self.frame_index
            self.frame_index += 1
            f.write(struct.pack("<B", frame_type))
            f.write(struct.pack("<H", parent_id))
            f.write(struct.pack("<3f", pos.x, pos.z, pos.y))
            f.write(struct.pack("<3f", scale.x, scale.z, scale.y))
            f.write(struct.pack("<4f", rot.w, rot.x, rot.z, rot.y))
            f.write(struct.pack("<B", 0))
            self.write_string(f, bone.name)
            self.write_string(f, "")
            self.serialize_joint(f, bone, armature, parent_id)
    def collect_lods(self):
        all_lod_objects = set()
        for obj in self.objects_to_export:
            if obj.type != "MESH" or "_lod" not in obj.name:
                continue
            base_name = obj.name.split("_lod")[0]
            base_obj = next((o for o in self.objects_to_export if o.name == base_name and o.type == "MESH"), None)
            if base_obj:
                if base_obj not in self.lod_map:
                    self.lod_map[base_obj] = [base_obj]
                lod_num = int(obj.name.split("_lod")[1])
                if lod_num >= 1:
                    all_lod_objects.add(obj)
                    while len(self.lod_map[base_obj]) <= lod_num:
                        self.lod_map[base_obj].append(None)
                    self.lod_map[base_obj][lod_num] = obj
        for base_obj in self.lod_map:
            self.lod_map[base_obj] = [lod for lod in self.lod_map[base_obj] if lod is not None]
        return all_lod_objects
    def serialize_file(self):
        with open(self.filepath, "wb") as f:
            self.serialize_header(f)
            self.materials = self.collect_materials()
            f.write(struct.pack("<H", len(self.materials)))
            for i, mat in enumerate(self.materials):
                self.serialize_material(f, mat, i + 1)
            lod_objects = self.collect_lods()
            self.objects = [
                obj for obj in self.objects_to_export
                if obj.type in ("MESH", "EMPTY") and obj not in lod_objects
            ]
            armatures = [obj for obj in self.objects_to_export if obj.type == "ARMATURE"]
            total_frames = len(self.objects) + sum(len(arm.data.bones) for arm in armatures)
            f.write(struct.pack("<H", total_frames))
            for obj in self.objects:
                self.serialize_frame(f, obj)
            for armature in armatures:
                self.frames_map[armature] = self.frame_index
                self.serialize_joints(f, armature)
            f.write(struct.pack("<?", False))
class The4DSImporter:
    def __init__(self, filepath):
        self.filepath = filepath
        dir_path = os.path.dirname(filepath)
        self.base_dir = os.path.abspath(os.path.join(dir_path, "..", ".."))
        print(f"Base directory set to: {self.base_dir}")
        if not os.path.exists(os.path.join(self.base_dir, "maps")):
            print(f"Warning: 'maps' folder not found at {os.path.join(self.base_dir, 'maps')}. Textures may not load.")
        self.version = 0
        self.materials = []
        self.skinned_meshes = []
        self.frames_map = {}
        self.frame_index = 1
        self.joints = []
        self.bone_nodes = {}
        self.base_bone_name = None
        self.bones_map = {}
        self.armature = None
        self.parenting_info = []
        self.frame_types = {}
        self.texture_cache = {}
    def import_file(self):
        with open(self.filepath, "rb") as f:
            header = f.read(4)
            if header != b"4DS\0":
                print("Error: Not a valid 4DS file (invalid header)")
                return
            self.version = struct.unpack("<H", f.read(2))[0]
            if self.version != VERSION_MAFIA:
                print(f"Error: Unsupported 4DS version {self.version}. Only version {VERSION_MAFIA} (Mafia) is supported.")
                return
            f.read(8)
            mat_count = struct.unpack("<H", f.read(2))[0]
            print(f"Reading {mat_count} materials...")
            self.materials = []
            for _ in range(mat_count):
                mat = self.deserialize_material(f)
                self.materials.append(mat)
            frame_count = struct.unpack("<H", f.read(2))[0]
            print(f"Reading {frame_count} frames...")
            frames = []
            for i in range(frame_count):
                print(f"Processing frame {i+1}/{frame_count}...")
                if not self.deserialize_frame(f, self.materials, frames):
                    print(f"Failed to deserialize frame {i+1}")
                    continue
            if self.armature and self.joints:
                print("Building armature...")
                self.build_armature()
                print("Applying skinning...")
                for mesh, vertex_groups, bone_to_parent in self.skinned_meshes:
                    self.apply_skinning(mesh, vertex_groups, bone_to_parent)
            print("Applying parenting...")
            self.apply_deferred_parenting()
            is_animated = struct.unpack("<B", f.read(1))[0]
            if is_animated:
                print("Animation data present (not supported)")
            print("Import completed.")
    def parent_to_bone(self, obj, bone_name):
        bpy.ops.object.select_all(action="DESELECT")
        self.armature.select_set(True)
        bpy.context.view_layer.objects.active = self.armature
        bpy.ops.object.mode_set(mode="EDIT")
        if bone_name not in self.armature.data.edit_bones:
            print(f"Error: Bone {bone_name} not found in armature during parenting")
            bpy.ops.object.mode_set(mode="OBJECT")
            return
        edit_bone = self.armature.data.edit_bones[bone_name]
        self.armature.data.edit_bones.active = edit_bone
        bone_matrix = Matrix(edit_bone.matrix)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        self.armature.select_set(True)
        bpy.context.view_layer.objects.active = self.armature
        bone_matrix_tr = Matrix.Translation(bone_matrix.to_translation())
        obj.matrix_basis = self.armature.matrix_world @ bone_matrix_tr @ obj.matrix_basis
        bpy.ops.object.parent_set(type="BONE", xmirror=False, keep_transform=True)
    def read_string_fixed(self, f, length):
        bytes_data = f.read(length)
        unpacked = struct.unpack(f"{length}c", bytes_data)
        return "".join(c.decode("windows-1250", errors='replace') for c in unpacked)
    def read_string(self, f):
        length = struct.unpack("B", f.read(1))[0]
        return self.read_string_fixed(f, length) if length > 0 else ""
    def get_color_key(self, filepath):
        """
        Reads Index 0 from BMP palette (Offset 54).
        Returns linear RGB tuple.
        """
        if not os.path.exists(filepath):
            return None
            
        try:
            with open(filepath, "rb") as f:
                # BMP Header
                if f.read(2) != b'BM': return None
                f.seek(28) # Bit count
                bit_count = struct.unpack("<H", f.read(2))[0]
                
                # Only 8-bit (256 colors) or lower have palettes
                if bit_count <= 8:
                    # Palette is usually at offset 54 (14 header + 40 info header)
                    f.seek(54)
                    # Read Index 0: Blue, Green, Red, Reserved
                    b, g, r, _ = struct.unpack("<BBBB", f.read(4))
                    
                    # Convert to Linear for Blender
                    def srgb_to_lin(c):
                        v = c / 255.0
                        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                        
                    return (srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b))
        except Exception as e:
            print(f"Error reading Color Key from {filepath}: {e}")
            
        return None
    
            
    def get_or_load_texture(self, filepath):
        norm_path = os.path.normpath(filepath.lower())
        if norm_path not in self.texture_cache:
            full_path = os.path.join(self.base_dir, "maps", os.path.basename(filepath))
            if os.path.exists(full_path):
                try:
                    image = bpy.data.images.load(full_path, check_existing=True)
                    self.texture_cache[norm_path] = image
                except Exception as e:
                    print(f"Warning: Failed to load texture {full_path}: {e}")
                    self.texture_cache[norm_path] = None
            else:
                print(f"Warning: Texture file not found: {full_path}")
                self.texture_cache[norm_path] = None
        return self.texture_cache[norm_path]
    def set_material_data(
        self, material, diffuse, alpha_tex, env_tex, emission, alpha, metallic, use_color_key
    ):
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        output = nodes.new("ShaderNodeOutputMaterial")
        principled.location = (0, 0)
        output.location = (300, 0)
        principled.inputs["Emission Color"].default_value = (*emission, 1.0)
        principled.inputs["Metallic"].default_value = 0.0
        principled.inputs["Specular IOR Level"].default_value = 0.0
        principled.inputs["Roughness"].default_value = 1.0
        base_color_input = principled.inputs["Base Color"]
        if diffuse:
            diffuse = diffuse.lower()
            tex_image = nodes.new("ShaderNodeTexImage")
            tex_image.image = self.get_or_load_texture(diffuse)
            tex_image.location = (-300, 0)
         
            if tex_image.image:
                links.new(tex_image.outputs["Color"], principled.inputs["Base Color"])
            if use_color_key:
                color_key = self.get_color_key(os.path.join(self.base_dir, "maps", diffuse))
                if color_key:
                    normalized_sum = color_key[0] + color_key[1] + color_key[2]
                    threshold_value = 0.3 if diffuse == "2kolo3.bmp" else 0.015 + 0.45 * normalized_sum
                    separate_rgb = nodes.new("ShaderNodeSeparateColor")
                    separate_rgb.location = (-100, 200)
                    links.new(tex_image.outputs["Color"], separate_rgb.inputs["Color"])
                    math_r = nodes.new("ShaderNodeMath")
                    math_r.operation = "SUBTRACT"
                    math_r.inputs[0].default_value = color_key[0]
                    links.new(separate_rgb.outputs["Red"], math_r.inputs[1])
                    math_g = nodes.new("ShaderNodeMath")
                    math_g.operation = "SUBTRACT"
                    math_g.inputs[0].default_value = color_key[1]
                    links.new(separate_rgb.outputs["Green"], math_g.inputs[1])
                    math_b = nodes.new("ShaderNodeMath")
                    math_b.operation = "SUBTRACT"
                    math_b.inputs[0].default_value = color_key[2]
                    links.new(separate_rgb.outputs["Blue"], math_b.inputs[1])
                    add_rg = nodes.new("ShaderNodeMath")
                    add_rg.operation = "ADD"
                    links.new(math_r.outputs["Value"], add_rg.inputs[0])
                    links.new(math_g.outputs["Value"], add_rg.inputs[1])
                    add_rgb = nodes.new("ShaderNodeMath")
                    add_rgb.operation = "ADD"
                    links.new(add_rg.outputs["Value"], add_rgb.inputs[0])
                    links.new(math_b.outputs["Value"], add_rgb.inputs[1])
                    threshold = nodes.new("ShaderNodeMath")
                    threshold.operation = "LESS_THAN"
                    threshold.inputs[1].default_value = threshold_value
                    links.new(add_rgb.outputs["Value"], threshold.inputs[0])
                    transparent = nodes.new("ShaderNodeBsdfTransparent")
                    mix_shader = nodes.new("ShaderNodeMixShader")
                    mix_shader.location = (150, 100)
                    links.new(threshold.outputs["Value"], mix_shader.inputs["Fac"])
                    links.new(transparent.outputs["BSDF"], mix_shader.inputs[1])
                    links.new(principled.outputs["BSDF"], mix_shader.inputs[2])
                    links.new(mix_shader.outputs["Shader"], output.inputs["Surface"])
                    material.blend_method = "CLIP"
                else:
                    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
            else:
                links.new(principled.outputs["BSDF"], output.inputs["Surface"])
        if alpha_tex:
            alpha_tex = alpha_tex.lower()
            alpha_tex_image = nodes.new("ShaderNodeTexImage")
            alpha_tex_image.image = self.get_or_load_texture(alpha_tex)
            alpha_tex_image.location = (-300, -300)
            if alpha_tex_image.image:
                links.new(alpha_tex_image.outputs["Color"], principled.inputs["Alpha"])
                links.new(principled.outputs["BSDF"], output.inputs["Surface"])
                material.blend_method = "BLEND"
        if env_tex:
            env_tex = env_tex.lower()
            env_image = nodes.new("ShaderNodeTexImage")
            env_image.image = self.get_or_load_texture(env_tex)
            if env_image.image:
                env_image.projection = "SPHERE"
                env_image.location = (-300, -600)
                tex_coord = nodes.new("ShaderNodeTexCoord")
                mapping = nodes.new("ShaderNodeMapping")
                mapping.vector_type = 'TEXTURE'
                tex_coord.location = (-700, -600)
                mapping.location = (-500, -600)
                links.new(tex_coord.outputs["Reflection"], mapping.inputs["Vector"])
                links.new(mapping.outputs["Vector"], env_image.inputs["Vector"])
                mix_rgb = nodes.new("ShaderNodeMixRGB")
                mix_rgb.blend_type = 'ADD'
                mix_rgb.inputs["Fac"].default_value = metallic
                mix_rgb.location = (-100, -300)
                if diffuse:
                    links.new(tex_image.outputs["Color"], mix_rgb.inputs["Color1"])
                else:
                    mix_rgb.inputs["Color1"].default_value = (1.0, 1.0, 1.0, 1.0)
                links.new(env_image.outputs["Color"], mix_rgb.inputs["Color2"])
                links.new(mix_rgb.outputs["Color"], base_color_input)
        if principled.inputs["Alpha"].default_value < 1.0 or alpha_tex:
            material.blend_method = "BLEND"
        if not output.inputs["Surface"].is_linked:
            links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    
                                                           
    def build_armature(self):
        if not self.armature or not self.joints:
            return
        bpy.context.view_layer.objects.active = self.armature
        bpy.ops.object.mode_set(mode="EDIT")
        armature = self.armature.data
        armature.display_type = "OCTAHEDRAL"
     
        # Key: Frame ID, Value: Blender Matrix
        world_matrices = {}
     
        # Base Bone (Root Identity)
        base_bone = armature.edit_bones[self.base_bone_name]
        world_matrices[1] = Matrix.Identity(4)
     
        bone_map = {self.base_bone_name: base_bone}
        # 1. Calculate World Matrices & Place Heads
        for name, local_matrix, parent_id, bone_id in self.joints:
            bone = armature.edit_bones.new(name)
            bone_map[name] = bone
         
            # Store scale for leaf calculation
            bone["file_scale"] = local_matrix.to_scale()
            # Logic: World = Parent_World @ Local
            parent_matrix = world_matrices.get(parent_id, Matrix.Identity(4))
         
            current_world_matrix = parent_matrix @ local_matrix
         
            # Store world matrix for children
            frame_index = -1
            for idx, fname in self.frames_map.items():
                if fname == name:
                    frame_index = idx
                    break
            if frame_index != -1:
                world_matrices[frame_index] = current_world_matrix
         
            # Apply Matrix (Sets Head and Orientation)
            bone.matrix = current_world_matrix
         
            # Parenting
            if parent_id == 1:
                bone.parent = base_bone
            else:
                parent_name = self.frames_map.get(parent_id)
                if isinstance(parent_name, str) and parent_name in bone_map:
                    bone.parent = bone_map[parent_name]
                else:
                    bone.parent = base_bone
        # 2. Fix Visuals (Prevent Collapsing)
        for bone in armature.edit_bones:
            if bone.name == self.base_bone_name:
                continue
            # Retrieve scale safely
            scl_prop = bone.get("file_scale")
            scl_vec = Vector(scl_prop) if scl_prop else Vector((1, 1, 1))
            max_scl = max(scl_vec.x, scl_vec.y, scl_vec.z)
            if max_scl < 0.01: max_scl = 1.0 # Prevent zero scale issues
            # Standard Bone Length
            target_length = 0.15 * max_scl
            if target_length < 0.05: target_length = 0.05
            # Get the forward direction from the matrix (Y-Axis is forward in Blender Bones)
            # We use this as a fallback if snapping fails
            matrix_forward = bone.matrix.to_quaternion() @ Vector((0, 1, 0))
            if bone.children:
                # Try snapping to average of children
                avg_child_head = Vector((0, 0, 0))
                for child in bone.children:
                    avg_child_head += child.head
                avg_child_head /= len(bone.children)
             
                # Check distance. If children are at the EXACT same spot as parent (pivot),
                # we must NOT snap, otherwise the parent collapses to a point.
                if (avg_child_head - bone.head).length > 0.001:
                    bone.tail = avg_child_head
                    bone.use_connect = True
                else:
                    # Fallback: Extend along the Rotation Axis
                    bone.tail = bone.head + matrix_forward * target_length
            else:
                # Leaf Bone: Always extend along the Rotation Axis
                bone.tail = bone.head + matrix_forward * target_length
        bpy.ops.object.mode_set(mode="OBJECT")
    def apply_skinning(self, mesh, vertex_groups, bone_to_parent):
        mod = mesh.modifiers.new(name="Armature", type="ARMATURE")
        mod.object = self.armature
        total_vertices = len(mesh.data.vertices)
        vertex_counter = 0
        if vertex_groups:
            lod_vertex_groups = vertex_groups[0]
            bone_nodes = self.bone_nodes
            bone_names = sorted(
                bone_nodes.items(), key=lambda x: x[0]
            ) # Ensure order: [(0, "back1"), (1, "back2"), ...]
            bone_name_list = [
                name for _, name in bone_names
            ] # ["back1", "back2", "back3", "l_shoulder", ...]
            for bone_id, num_locked, weights in lod_vertex_groups:
                if bone_id < len(bone_name_list):
                    bone_name = bone_name_list[bone_id]
                else:
                    print(
                        f"Warning: Bone ID {bone_id} exceeds available bone names ({len(bone_name_list)})"
                    )
                    bone_name = f"unknown_bone_{bone_id}"
                bvg = mesh.vertex_groups.get(bone_name)
                if not bvg:
                    bvg = mesh.vertex_groups.new(name=bone_name)
                locked_vertices = list(
                    range(vertex_counter, vertex_counter + num_locked)
                )
                if locked_vertices:
                    bvg.add(locked_vertices, 1.0, "ADD")
                vertex_counter += num_locked
                weighted_vertices = list(
                    range(vertex_counter, vertex_counter + len(weights))
                )
                for i, w in zip(weighted_vertices, weights):
                    if i < total_vertices:
                        bvg.add([i], w, "REPLACE")
                    else:
                        print(
                            f"Warning: Vertex index {i} out of range ({total_vertices})"
                        )
                vertex_counter += len(weights)
            base_vg = mesh.vertex_groups.get(self.base_bone_name)
            if not base_vg:
                base_vg = mesh.vertex_groups.new(name=self.base_bone_name)
            base_vertices = list(range(vertex_counter, total_vertices))
            if base_vertices:
                base_vg.add(base_vertices, 1.0, "ADD")
    
    def deserialize_singlemesh(self, f, num_lods, mesh):
        armature_name = mesh.name
        if not self.armature:
            armature_data = bpy.data.armatures.new(armature_name + "_bones")
            armature_data.display_type = "OCTAHEDRAL"
            self.armature = bpy.data.objects.new(armature_name, armature_data)
            self.armature.show_in_front = True
            bpy.context.collection.objects.link(self.armature)
            bpy.context.view_layer.objects.active = self.armature
            bpy.ops.object.mode_set(mode="EDIT")
            base_bone = self.armature.data.edit_bones.new(armature_name)
         
            # FIX: Base bone goes from -Y to 0.
            # This ensures the Root Bone (at 0,0,0) connects to the Tail of this bone.
            base_bone.head = Vector((0, -0.25, 0))
            base_bone.tail = Vector((0, 0, 0))
         
            self.base_bone_name = base_bone.name
            bpy.ops.object.mode_set(mode="OBJECT")
        mesh.name = armature_name
        self.armature.name = armature_name + "_armature"
        self.armature.parent = mesh
        vertex_groups = []
        bone_to_parent = {}
        for lod_id in range(num_lods):
            num_bones = struct.unpack("<B", f.read(1))[0]
            num_non_weighted_verts = struct.unpack("<I", f.read(4))[0]
            min_bounds = struct.unpack("<3f", f.read(12))
            max_bounds = struct.unpack("<3f", f.read(12))
            lod_vertex_groups = []
            sequential_bone_id = 0
            for _ in range(num_bones):
                inverse_transform = struct.unpack("<16f", f.read(64))
                num_locked = struct.unpack("<I", f.read(4))[0]
                num_weighted = struct.unpack("<I", f.read(4))[0]
                file_bone_id = struct.unpack("<I", f.read(4))[0]
                bone_min = struct.unpack("<3f", f.read(12))
                bone_max = struct.unpack("<3f", f.read(12))
                weights = list(struct.unpack(f"<{num_weighted}f", f.read(4 * num_weighted)))
                bone_id = sequential_bone_id
                sequential_bone_id += 1
                parent_id = 0
                for _, _, pid, bid in self.joints:
                    if bid == file_bone_id:
                        parent_id = pid
                        break
                bone_to_parent[bone_id] = parent_id
                lod_vertex_groups.append((bone_id, num_locked, weights))
            vertex_groups.append(lod_vertex_groups)
        self.skinned_meshes.append((mesh, vertex_groups, bone_to_parent))
        return vertex_groups
         
    def deserialize_dummy(self, f, empty, pos, rot, scale):
        min_bounds = struct.unpack("<3f", f.read(12))
        max_bounds = struct.unpack("<3f", f.read(12))
        min_bounds = (min_bounds[0], min_bounds[2], min_bounds[1])
        max_bounds = (max_bounds[0], max_bounds[2], max_bounds[1])
        aabb_size = (
            max_bounds[0] - min_bounds[0],
            max_bounds[1] - min_bounds[1],
            max_bounds[2] - min_bounds[2],
        )
        display_size = max(aabb_size[0], aabb_size[1], aabb_size[2]) * 0.5
        empty.empty_display_type = "CUBE"
        empty.empty_display_size = display_size
        empty.show_name = True
        empty.location = pos
        empty.rotation_mode = "QUATERNION"
        empty.rotation_quaternion = (rot[0], rot[1], rot[3], rot[2])
        empty.scale = scale
        empty["bbox_min"] = min_bounds
        empty["bbox_max"] = max_bounds
    def deserialize_target(self, f, empty, pos, rot, scale):
        unknown = struct.unpack("<H", f.read(2))[0]
        num_links = struct.unpack("<B", f.read(1))[0]
        link_ids = struct.unpack(
            f"<{num_links}H", f.read(2 * num_links)
        )
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.5
        empty.show_name = True
        empty.location = pos
        empty.rotation_mode = "QUATERNION"
        empty.rotation_quaternion = (rot[0], rot[1], rot[3], rot[2])
        empty.scale = scale
        empty["link_ids"] = list(link_ids)
    def deserialize_morph(self, f, mesh, num_vertices_per_lod):
            num_targets = struct.unpack("<B", f.read(1))[0]
            if num_targets == 0:
                return
            num_channels = struct.unpack("<B", f.read(1))[0]
            num_lods = struct.unpack("<B", f.read(1))[0]
            if len(num_vertices_per_lod) != num_lods:
                num_lods = min(num_lods, len(num_vertices_per_lod))
            morph_data = []
            for lod_idx in range(num_lods):
                lod_data = []
                for channel_idx in range(num_channels):
                    num_morph_vertices = struct.unpack("<H", f.read(2))[0]
                    if num_morph_vertices == 0:
                        lod_data.append([])
                        continue
                    vertex_data = []
                    for vert_idx in range(num_morph_vertices):
                        targets = []
                        for target_idx in range(num_targets):
                            p = struct.unpack("<3f", f.read(12))
                            n = struct.unpack("<3f", f.read(12))
                            # Convert coordinate system (Swap Y and Z)
                            p = (p[0], p[2], p[1])
                            n = (n[0], n[2], n[1])
                            targets.append((p, n))
                        vertex_data.append(targets)
                    unknown = struct.unpack("<?", f.read(1))[0]
                    vertex_indices = []
                    if unknown:
                        vertex_indices = struct.unpack(
                            f"<{num_morph_vertices}H", f.read(2 * num_morph_vertices)
                        )
                    else:
                        vertex_indices = list(range(num_morph_vertices))
                    lod_data.append((vertex_data, vertex_indices))
                morph_data.append(lod_data)
                min_bounds = struct.unpack("<3f", f.read(12))
                max_bounds = struct.unpack("<3f", f.read(12))
                center = struct.unpack("<3f", f.read(12))
                dist = struct.unpack("<f", f.read(4))
            # Apply shape keys to mesh
            if not mesh.data.shape_keys:
                mesh.shape_key_add(name="Basis", from_mix=False)
            for lod_idx in range(num_lods):
                num_vertices = num_vertices_per_lod[lod_idx]
                if len(mesh.data.vertices) != num_vertices:
                    continue
                lod_data = morph_data[lod_idx]
                for channel_idx in range(num_channels):
                    if not lod_data[channel_idx]:
                        continue
                    vertex_data, vertex_indices = lod_data[channel_idx]
                    for target_idx in range(num_targets):
                        shape_key_name = (
                            f"Target_{target_idx}_LOD{lod_idx}_Channel{channel_idx}"
                        )
                        shape_key = mesh.shape_key_add(name=shape_key_name, from_mix=False)
                        for morph_idx, vert_idx in enumerate(vertex_indices):
                            if vert_idx >= num_vertices:
                                continue
                            target_pos, _ = vertex_data[morph_idx][target_idx]
                            shape_key.data[vert_idx].co = target_pos
    def apply_deferred_parenting(self):
        for frame_index, parent_id in self.parenting_info:
            if frame_index not in self.frames_map:
                print(f"Warning: Frame {frame_index} not found in frames_map")
                continue
            if frame_index == parent_id:
                print(f"Ignoring frame {frame_index} - parent set to itself")
                continue
            parent_type = self.frame_types.get(parent_id, 0)
            child_obj = self.frames_map[frame_index]
            if child_obj is None or isinstance(
                child_obj, str
            ):
                print(
                    f"Skipping parenting for frame {frame_index}: Not a valid object (value: {child_obj})"
                )
                continue
            if parent_id not in self.frames_map:
                print(
                    f"Warning: Parent {parent_id} for frame {frame_index} not found in frames_map"
                )
                continue
            parent_entry = self.frames_map[parent_id]
            if parent_type == FRAME_JOINT:
                if not self.armature:
                    print(
                        f"Warning: No armature available to parent frame {frame_index} to joint {parent_id}"
                    )
                    continue
                parent_bone_name = self.bones_map.get(parent_id)
                if not parent_bone_name:
                    print(f"Warning: Bone for joint {parent_id} not found in bones_map")
                    continue
                if parent_bone_name not in self.armature.data.bones:
                    print(f"Warning: Bone {parent_bone_name} not found in armature")
                    continue
                self.parent_to_bone(child_obj, parent_bone_name)
            else:
                if isinstance(parent_entry, str):
                    print(
                        f"Warning: Parent {parent_id} is a joint but frame type is {parent_type}"
                    )
                    continue
                parent_obj = parent_entry
                child_obj.parent = parent_obj
    def deserialize_material(self, f):
        mat = bpy.data.materials.new("LS3D_Material")
        mat.use_nodes = True
        tree = mat.node_tree
        tree.nodes.clear()

        # 1. READ RAW DATA
        flags = struct.unpack("<I", f.read(4))[0]
        
        # Colors (Linear Float)
        raw_amb = struct.unpack("<3f", f.read(12))
        raw_diff = struct.unpack("<3f", f.read(12))
        raw_emit = struct.unpack("<3f", f.read(12))
        
        opacity = struct.unpack("<f", f.read(4))[0]
        
        env_opacity = 0.0
        env_tex_name = ""
        
        if flags & MTL_ENVMAP:
            env_opacity = struct.unpack("<f", f.read(4))[0]
            env_tex_name = self.read_string(f).lower()
            
        diffuse_tex_name = self.read_string(f).lower()
        if len(diffuse_tex_name) > 0:
            mat.name = diffuse_tex_name
            
        alpha_tex_name = ""
        if (flags & MTL_ADDEFFECT) and (flags & MTL_ALPHATEX):
            alpha_tex_name = self.read_string(f).lower()

        # Skip Animation Data if present
        if flags & MTL_ANIMTEXALPHA: f.read(14)
        if flags & MTL_ANIMTEXDIFF: f.read(14)

        # 2. SETUP NODE GROUP
        ls3d_group = get_or_create_ls3d_group()
        group_node = tree.nodes.new('ShaderNodeGroup')
        group_node.node_tree = ls3d_group
        group_node.location = (0, 0)
        group_node.width = 280
        
        # 3. SET VALUES
        group_node.inputs["Environment Color"].default_value = (*raw_amb, 1.0)
        group_node.inputs["Diffuse Color"].default_value = (*raw_diff, 1.0)
        group_node.inputs["Emission Color"].default_value = (*raw_emit, 1.0)
        group_node.inputs["Opacity"].default_value = opacity
        group_node.inputs["Env Intensity"].default_value = env_opacity
        
        # 4. SET FLAGS
        # MTL_UNLIT is Bit 0 (0x1)
        group_node.inputs["F: Unlit"].default_value = 1.0 if (flags & MTL_UNLIT) else 0.0 
        group_node.inputs["F: Double Sided"].default_value = 1.0 if (flags & MTL_DOUBLESIDED) else 0.0
        group_node.inputs["F: Colored"].default_value = 1.0 if (flags & MTL_COLORED) else 0.0
        group_node.inputs["F: Color Key"].default_value = 1.0 if (flags & MTL_COLORKEY) else 0.0
        group_node.inputs["F: Add Effect (Alpha)"].default_value = 1.0 if (flags & MTL_ADDEFFECT) else 0.0
        group_node.inputs["F: Env Map"].default_value = 1.0 if (flags & MTL_ENVMAP) else 0.0
        group_node.inputs["F: Disable Z-Write"].default_value = 1.0 if (flags & MTL_ADDITIVEMIX) else 0.0
        group_node.inputs["F: Mip Map"].default_value = 1.0 if (flags & MTL_MIPMAP) else 0.0

        # Output
        output = tree.nodes.new('ShaderNodeOutputMaterial')
        output.location = (350, 0)
        tree.links.new(group_node.outputs["BSDF"], output.inputs["Surface"])

        # 5. LOAD TEXTURES
        if diffuse_tex_name:
            tex_node = tree.nodes.new('ShaderNodeTexImage')
            tex_node.image = self.get_or_load_texture(diffuse_tex_name)
            tex_node.location = (-350, 100)
            if flags & MTL_COLORKEY:
                tex_node.interpolation = 'Closest' 
            tree.links.new(tex_node.outputs["Color"], group_node.inputs["Diffuse Color"])
            
            # Color Key Logic
            if flags & MTL_COLORKEY:
                mat.blend_method = 'CLIP'
                mat.alpha_threshold = 0.5
                full_path = os.path.join(self.base_dir, "maps", diffuse_tex_name)
                key_color = self.get_color_key(full_path)
                if key_color:
                    group_node.inputs["Color Key Value"].default_value = (*key_color, 1.0)
            
            # Alpha Logic
            if alpha_tex_name:
                alpha_node = tree.nodes.new('ShaderNodeTexImage')
                alpha_node.image = self.get_or_load_texture(alpha_tex_name)
                alpha_node.location = (-350, -150)
                tree.links.new(alpha_node.outputs["Color"], group_node.inputs["Opacity"])
                mat.blend_method = 'BLEND'
            elif (flags & MTL_ADDEFFECT) and not (flags & MTL_ALPHATEX):
                 tree.links.new(tex_node.outputs["Alpha"], group_node.inputs["Opacity"])
                 mat.blend_method = 'BLEND'

        mat.use_backface_culling = not (flags & MTL_DOUBLESIDED)
        
        return mat

    def deserialize_object(self, f, materials, mesh, mesh_data):
        instance_id = struct.unpack("<H", f.read(2))[0]
        if instance_id > 0:
            return None, None
        vertices_per_lod = []
        num_lods = struct.unpack("<B", f.read(1))[0]
        
        for lod_idx in range(num_lods):
            if lod_idx > 0:
                name = f"{mesh.name}_lod{lod_idx}"
                mesh_data = bpy.data.meshes.new(name)
                new_mesh = bpy.data.objects.new(name, mesh_data)
                new_mesh.parent = mesh
                bpy.context.collection.objects.link(new_mesh)
                mesh = new_mesh
            
            clipping_range = struct.unpack("<f", f.read(4))[0]
            mesh.ls3d_lod_dist = clipping_range
            
            num_vertices = struct.unpack("<H", f.read(2))[0]
            vertices_per_lod.append(num_vertices)
            
            bm = bmesh.new()
            vertices = []
            raw_verts = []
            
            for _ in range(num_vertices):
                pos = struct.unpack("<3f", f.read(12))
                norm = struct.unpack("<3f", f.read(12))
                uv = struct.unpack("<2f", f.read(8))
                
                vert = bm.verts.new((pos[0], pos[2], pos[1]))
                
                raw_verts.append({
                    'uv': (uv[0], 1.0 - uv[1]), 
                    'norm': (norm[0], norm[2], norm[1])
                })
                vertices.append(vert)
                
            bm.verts.ensure_lookup_table()
            
            num_face_groups = struct.unpack("<B", f.read(1))[0]
            for group_idx in range(num_face_groups):
                num_faces = struct.unpack("<H", f.read(2))[0]
                mesh_data.materials.append(None)
                slot_idx = len(mesh_data.materials) - 1
                for _ in range(num_faces):
                    idxs = struct.unpack("<3H", f.read(6))
                    idxs_swap = (idxs[0], idxs[2], idxs[1])
                    try:
                        face = bm.faces.new([vertices[i] for i in idxs_swap])
                        face.material_index = slot_idx
                        face.smooth = True # Essential to allow custom normals to render
                    except: pass
                        
                mat_idx = struct.unpack("<H", f.read(2))[0]
                if mat_idx > 0 and mat_idx - 1 < len(materials):
                    mesh_data.materials[slot_idx] = materials[mat_idx - 1]
            
            bm.to_mesh(mesh_data)
            bm.free()
            
            # --- APPLY DATA ---
            uv_layer = mesh_data.uv_layers.new()
            custom_normals = []
            
            # Iterate loops (corners) to apply UVs and Normals
            for loop in mesh_data.loops:
                vert_idx = loop.vertex_index
                if uv_layer:
                    uv_layer.data[loop.index].uv = raw_verts[vert_idx]['uv']
                custom_normals.append(raw_verts[vert_idx]['norm'])
            
            # Apply Custom Normals
            try:
                mesh_data.normals_split_custom_set(custom_normals)
            except AttributeError: pass 
            
            if hasattr(mesh_data, "use_auto_smooth"):
                mesh_data.use_auto_smooth = True
            
            # Fix for Blender 5.0 validation
            mesh_data.validate(clean_customdata=False)
            
            if lod_idx > 0:
                mesh.hide_set(True)
                mesh.hide_render = True
            
        return num_lods, vertices_per_lod
                    
    def deserialize_sector(self, f, mesh):
        # 1. Flags
        flags = struct.unpack("<2I", f.read(8))
        mesh.ls3d_sector_flags1 = flags[0]
        mesh.ls3d_sector_flags2 = flags[1]
        
        # 2. Geometry
        num_verts = struct.unpack("<I", f.read(4))[0]
        num_faces = struct.unpack("<I", f.read(4))[0]
        
        bm = bmesh.new()
        vertices = []
        for _ in range(num_verts):
            p = struct.unpack("<3f", f.read(12))
            # Swap Y/Z for Blender
            vert = bm.verts.new((p[0], p[2], p[1]))
            vertices.append(vert)
        bm.verts.ensure_lookup_table()
        
        for _ in range(num_faces):
            idxs = struct.unpack("<3H", f.read(6))
            try: bm.faces.new([vertices[idxs[0]], vertices[idxs[2]], vertices[idxs[1]]])
            except: pass
            
        bm.to_mesh(mesh.data)
        bm.free()
        
        # 3. Bounds (Mafia: Read AFTER mesh)
        min_b = struct.unpack("<3f", f.read(12))
        max_b = struct.unpack("<3f", f.read(12))
        mesh.bbox_min = (min_b[0], min_b[2], min_b[1])
        mesh.bbox_max = (max_b[0], max_b[2], max_b[1])
        
        # 4. Portals
        num_portals = struct.unpack("<B", f.read(1))[0]
        for i in range(num_portals):
            self.deserialize_portal(f, mesh, i)

    def deserialize_portal(self, f, parent_sector, index):
        # Byte 1: Num Verts
        num_verts = struct.unpack("<B", f.read(1))[0]
        
        # Mafia Order: Flags(I), Near(f), Far(f)
        flags = struct.unpack("<I", f.read(4))[0]
        near_r = struct.unpack("<f", f.read(4))[0]
        far_r = struct.unpack("<f", f.read(4))[0]
        
        # Plane: Normal(3f), Dot(f)
        normal = struct.unpack("<3f", f.read(12))
        dotp = struct.unpack("<f", f.read(4))[0]
        
        # Vertices
        verts = []
        for _ in range(num_verts):
            p = struct.unpack("<3f", f.read(12))
            verts.append((p[0], p[2], p[1]))
            
        # Create Object
        p_name = f"{parent_sector.name}_Portal_{index}"
        p_mesh = bpy.data.meshes.new(p_name)
        p_obj = bpy.data.objects.new(p_name, p_mesh)
        p_obj.parent = parent_sector
        bpy.context.collection.objects.link(p_obj)
        
        p_obj.ls3d_portal_flags = flags
        p_obj.ls3d_portal_near = near_r
        p_obj.ls3d_portal_far = far_r
        
        # Build Mesh
        bm = bmesh.new()
        for v in verts: bm.verts.new(v)
        bm.verts.ensure_lookup_table()
        if len(bm.verts) >= 3: bm.faces.new(bm.verts)
        bm.to_mesh(p_mesh)
        bm.free()

    def deserialize_frame(self, f, materials, frames):
        # 1. READ HEADER
        frame_type = struct.unpack("<B", f.read(1))[0]
        visual_type = 0
        visual_flags = (128, 42) # Default (RenderFlag1, RenderFlag2)
        
        if frame_type == FRAME_VISUAL:
            visual_type = struct.unpack("<B", f.read(1))[0]
            # Read 2 Bytes: Render Flags 1 and Render Flags 2
            visual_flags = struct.unpack("<2B", f.read(2))
            
        parent_id = struct.unpack("<H", f.read(2))[0]
     
        # 2. READ TRANSFORM
        position = struct.unpack("<3f", f.read(12))
        scale = struct.unpack("<3f", f.read(12))
        rot = struct.unpack("<4f", f.read(16)) # Quaternion (W, X, Y, Z)
        
        # Convert to Blender Coordinate System (Z-Up)
        pos = (position[0], position[2], position[1])
        scl = (scale[0], scale[2], scale[1])
        rot_tuple = (rot[0], rot[1], rot[3], rot[2])
        
        scale_mat = Matrix.Diagonal(scl).to_4x4()
        rot_mat = Quaternion(rot_tuple).to_matrix().to_4x4()
        trans_mat = Matrix.Translation(pos)
        transform_mat = trans_mat @ rot_mat @ scale_mat
        
        # 3. READ CULL FLAGS & STRINGS
        culling_flags = struct.unpack("<B", f.read(1))[0]
        name = self.read_string(f)
        user_props = self.read_string(f)
        
        # Register Frame ID
        self.frame_types[self.frame_index] = frame_type
        if parent_id > 0:
            self.parenting_info.append((self.frame_index, parent_id))
        
        mesh = None
        empty = None
        
        # --- 4. CREATE OBJECTS BASED ON TYPE ---
        
        if frame_type == FRAME_VISUAL:
            # A. Standard / Lit Objects
            if visual_type in (VISUAL_OBJECT, VISUAL_LITOBJECT):
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = str(visual_type)
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                self.frame_index += 1
                mesh.matrix_local = transform_mat
                self.deserialize_object(f, materials, mesh, mesh_data)
            
            # B. Billboard
            elif visual_type == VISUAL_BILLBOARD:
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = '4' # Billboard
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                self.frame_index += 1
                mesh.matrix_local = transform_mat
                
                # Read Mesh Data
                self.deserialize_object(f, materials, mesh, mesh_data)
                # Read Specific Billboard Props
                self.deserialize_billboard(f, mesh)

            # C. Mirror
            elif visual_type == VISUAL_MIRROR:
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = '8' # Mirror
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                self.frame_index += 1
                mesh.matrix_local = transform_mat
                
                # Mirror has its own geometry structure
                self.deserialize_mirror(f, mesh)

            # D. Skinned / Morph Objects
            elif visual_type in (VISUAL_SINGLEMESH, VISUAL_SINGLEMORPH, VISUAL_MORPH):
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = str(visual_type)
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                mesh.matrix_local = transform_mat
                
                # Read Geometry
                num_lods, verts_per_lod = self.deserialize_object(f, materials, mesh, mesh_data)
                
                # Read Skinning Data
                if visual_type != VISUAL_MORPH:
                    self.deserialize_singlemesh(f, num_lods, mesh)
                    self.bones_map[self.frame_index] = self.base_bone_name
                
                # Read Morph Data
                if visual_type != VISUAL_SINGLEMESH:
                    self.deserialize_morph(f, mesh, verts_per_lod)
                
                self.frame_index += 1
            
            # E. Fallback for others (Projector, Emitor, etc) to keep stream sync
            else:
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = str(visual_type)
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                self.frame_index += 1
                mesh.matrix_local = transform_mat
                try: 
                    self.deserialize_object(f, materials, mesh, mesh_data)
                except: 
                    print(f"Warning: Could not parse geometry for visual type {visual_type}")

        elif frame_type == FRAME_SECTOR:
            mesh_data = bpy.data.meshes.new(name)
            mesh = bpy.data.objects.new(name, mesh_data)
            bpy.context.collection.objects.link(mesh)
            frames.append(mesh)
            self.frames_map[self.frame_index] = mesh
            self.frame_index += 1
            mesh.matrix_local = transform_mat
            self.deserialize_sector(f, mesh)

        elif frame_type == FRAME_DUMMY:
            empty = bpy.data.objects.new(name, None)
            bpy.context.collection.objects.link(empty)
            frames.append(empty)
            self.frames_map[self.frame_index] = empty
            self.frame_index += 1
            self.deserialize_dummy(f, empty, pos, rot_tuple, scl)
            
        elif frame_type == FRAME_TARGET:
            empty = bpy.data.objects.new(name, None)
            bpy.context.collection.objects.link(empty)
            frames.append(empty)
            self.frames_map[self.frame_index] = empty
            self.frame_index += 1
            self.deserialize_target(f, empty, pos, rot_tuple, scl)
            
        elif frame_type == FRAME_OCCLUDER:
            mesh_data = bpy.data.meshes.new(name)
            mesh = bpy.data.objects.new(name, mesh_data)
            bpy.context.collection.objects.link(mesh)
            frames.append(mesh)
            self.frames_map[self.frame_index] = mesh
            self.frame_index += 1
            self.deserialize_occluder(f, mesh, pos, rot_tuple, scl)
            
        elif frame_type == FRAME_JOINT:
            _ = f.read(64) # Skip Matrix
            bone_id = struct.unpack("<I", f.read(4))[0]
            if self.armature:
                self.joints.append((name, transform_mat, parent_id, bone_id))
                self.bone_nodes[bone_id] = name
                self.bones_map[self.frame_index] = name
                self.frames_map[self.frame_index] = name
                self.frame_index += 1
        
        else:
            print(f"Unsupported frame type {frame_type} for '{name}'")
            return False
        
        # --- 5. APPLY FLAGS & PROPERTIES TO OBJECT ---
        target_obj = mesh if mesh else empty
        if target_obj:
            # Apply Cull Flags
            target_obj.cull_flags = culling_flags
            
            # Apply User Props (String)
            target_obj.ls3d_user_props = user_props
            # Legacy support
            target_obj["Frame Properties"] = user_props 
            
            # Apply Visual Flags (Render Flags)
            if frame_type == FRAME_VISUAL:
                target_obj.render_flags = visual_flags[0]  # Render Flag 1
                target_obj.render_flags2 = visual_flags[1] # Render Flag 2
                
        return True
    
    def deserialize_billboard(self, f, obj):
        # rotAxis (U32, 1-based), rotMode (U8, 1-based)
        rot_axis = struct.unpack("<I", f.read(4))[0]
        rot_mode = struct.unpack("<B", f.read(1))[0]
        
        # Map to 0-based Enum
        obj.rot_axis = str(max(0, rot_axis - 1))
        obj.rot_mode = str(max(0, rot_mode - 1))

    def deserialize_mirror(self, f, obj):
        # 1. Props
        dmin = struct.unpack("<3f", f.read(12))
        dmax = struct.unpack("<3f", f.read(12))
        center = struct.unpack("<3f", f.read(12))
        radius = struct.unpack("<f", f.read(4))[0]
        
        # Matrix (16 floats)
        mat_floats = struct.unpack("<16f", f.read(64))
        
        # Color (3 floats)
        rgb = struct.unpack("<3f", f.read(12))
        obj.mirror_color = rgb
        
        dist = struct.unpack("<f", f.read(4))[0]
        obj.mirror_dist = dist
        
        # 2. Mirror Mesh
        # It has its own geometry block inside the mirror struct
        num_verts = struct.unpack("<I", f.read(4))[0]
        num_faces = struct.unpack("<I", f.read(4))[0]
        
        bm = bmesh.new()
        vertices = []
        for _ in range(num_verts):
            p = struct.unpack("<3f", f.read(12))
            vertices.append(bm.verts.new((p[0], p[2], p[1])))
        bm.verts.ensure_lookup_table()
        
        for _ in range(num_faces):
            idxs = struct.unpack("<3H", f.read(6))
            try: bm.faces.new([vertices[idxs[0]], vertices[idxs[2]], vertices[idxs[1]]])
            except: pass
            
        bm.to_mesh(obj.data)
        bm.free()
    
class Export4DS(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.4ds"
    bl_label = "Export 4DS"
    filename_ext = ".4ds"
    filter_glob = StringProperty(default="*.4ds", options={"HIDDEN"})
    def execute(self, context):
        # Use selected objects if any, otherwise all objects in scene
        objects = context.selected_objects if context.selected_objects else context.scene.objects
        exporter = The4DSExporter(self.filepath, objects)
        exporter.serialize_file()
        return {"FINISHED"}
class Import4DS(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.4ds"
    bl_label = "Import 4DS"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".4ds"
    filter_glob = StringProperty(default="*.4ds", options={"HIDDEN"})
    def execute(self, context):
        importer = The4DSImporter(self.filepath)
        importer.import_file()
        return {"FINISHED"}
def menu_func_import(self, context):
    self.layout.operator(Import4DS.bl_idname, text="4DS Model File (.4ds)")
def menu_func_export(self, context):
    self.layout.operator(Export4DS.bl_idname, text="4DS Model File (.4ds)")

# --- HELPER FUNCTIONS ---
def get_flag_bit(self, prop_name, bit_index):
    return (getattr(self, prop_name, 0) & (1 << bit_index)) != 0

def set_flag_bit(self, value, prop_name, bit_index):
    current = getattr(self, prop_name, 0)
    if value:
        setattr(self, prop_name, current | (1 << bit_index))
    else:
        setattr(self, prop_name, current & ~(1 << bit_index))

def make_getter(prop_name, bit_index):
    return lambda self: get_flag_bit(self, prop_name, bit_index)

def make_setter(prop_name, bit_index):
    return lambda self, value: set_flag_bit(self, value, prop_name, bit_index)

def register():
    # 1. Visual Type
    bpy.types.Object.visual_type = EnumProperty(
        name="Mesh Type",
        items=(
            ('0', "Object", "Standard static mesh"),
            ('1', "Lit Object", "Object with pre-calculated lighting"),
            ('2', "Single Mesh", "Mesh with armature"),
            ('3', "Single Morph", "Mesh with armature and morphs"),
            ('4', "Billboard", "Always faces camera"),
            ('5', "Morph", "Morph targets only"),
            ('6', "Lens", "Lens flare"),
            ('7', "Projector", "Light projector"),
            ('8', "Mirror", "Reflection surface"),
            ('9', "Emitor", "Particle emitter"),
            ('10', "Shadow", "Shadow volume"),
            ('11', "Land Patch", "Landscape"),
        ),
        default='0'
    )

    # 2. Raw Flags (Integers)
    bpy.types.Object.cull_flags = IntProperty(name="Cull Flags", default=128, min=0, max=255, description="Raw value")
    bpy.types.Object.render_flags = IntProperty(name="Render Flags 1", default=128, min=0, max=255, description="Raw value")
    bpy.types.Object.render_flags2 = IntProperty(name="Render Flags 2", default=42, min=0, max=255, description="Raw value")

    # 3. Render Flags 2 Checkboxes (Matches Max4ds rltObject)
    bpy.types.Object.rf2_depth_bias = BoolProperty(name="Depth Bias", get=make_getter("render_flags2", 0), set=make_setter("render_flags2", 0))
    bpy.types.Object.rf2_shadowed = BoolProperty(name="Shadowed", get=make_getter("render_flags2", 1), set=make_setter("render_flags2", 1))
    bpy.types.Object.rf2_tex_proj = BoolProperty(name="Tex. Proj.", get=make_getter("render_flags2", 5), set=make_setter("render_flags2", 5))
    bpy.types.Object.rf2_no_fog = BoolProperty(name="No Fog", get=make_getter("render_flags2", 7), set=make_setter("render_flags2", 7))

    # 4. Cull Flags Checkboxes (Matches Max4ds rltObject)
    bpy.types.Object.cf_enabled = BoolProperty(name="(1) Enabled", get=make_getter("cull_flags", 0), set=make_setter("cull_flags", 0))
    for i in range(1, 8):
        setattr(bpy.types.Object, f"cf_unknown{i+1}", BoolProperty(name=f"({i+1}) Unknown", get=make_getter("cull_flags", i), set=make_setter("cull_flags", i)))

    # 5. String Params & LOD
    bpy.types.Object.ls3d_user_props = StringProperty(name="String Params", description="User defined property string")
    bpy.types.Object.ls3d_lod_dist = FloatProperty(name="Fadeout Distance", default=100.0, min=0.0)

    # 6. Portal Parameters
    bpy.types.Object.ls3d_portal_flags = IntProperty(name="Flags", default=4)
    bpy.types.Object.ls3d_portal_near = FloatProperty(name="Near Range", default=0.0)
    bpy.types.Object.ls3d_portal_far = FloatProperty(name="Far Range", default=100.0)
    bpy.types.Object.ls3d_portal_unknown = FloatProperty(name="Unknown", default=0.0)
    # Portal Enable (Bit 2 = Value 4)
    bpy.types.Object.ls3d_portal_enabled = BoolProperty(name="Enabled", get=make_getter("ls3d_portal_flags", 2), set=make_setter("ls3d_portal_flags", 2))

    # 7. Billboard & Mirror
    # Max: X, Z, Y -> 4DS: 0, 1, 2
    bpy.types.Object.rot_axis = EnumProperty(name="Rotation Axis", items=(('0', "X", ""), ('1', "Z", ""), ('2', "Y", "")), default='1')
    bpy.types.Object.rot_mode = EnumProperty(name="Rotation Mode", items=(('0', "All Axes", ""), ('1', "Single Axis", "")), default='0')
    
    bpy.types.Object.mirror_color = FloatVectorProperty(name="Background Color", subtype='COLOR', default=(0.0, 0.0, 0.0))
    bpy.types.Object.mirror_dist = FloatProperty(name="Active Range", default=100.0)

    # 8. Sector Flags
    bpy.types.Object.ls3d_sector_flags1 = IntProperty(name="Flags 1", default=2049)
    bpy.types.Object.ls3d_sector_flags2 = IntProperty(name="Flags 2", default=0)

    # BBox Storage
    bpy.types.Object.bbox_min = FloatVectorProperty(name="BBox Min", subtype='XYZ')
    bpy.types.Object.bbox_max = FloatVectorProperty(name="BBox Max", subtype='XYZ')
    
    bpy.utils.register_class(LS3D_OT_AddNode)
    bpy.utils.register_class(The4DSPanel)
    bpy.utils.register_class(Import4DS)
    bpy.utils.register_class(Export4DS)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    del bpy.types.Object.visual_type
    del bpy.types.Object.cull_flags
    del bpy.types.Object.render_flags
    del bpy.types.Object.render_flags2
    del bpy.types.Object.rf2_depth_bias
    del bpy.types.Object.rf2_shadowed
    del bpy.types.Object.rf2_tex_proj
    del bpy.types.Object.rf2_no_fog
    del bpy.types.Object.cf_enabled
    for i in range(1, 8):
        try: delattr(bpy.types.Object, f"cf_unknown{i+1}")
        except: pass
    
    del bpy.types.Object.ls3d_user_props
    del bpy.types.Object.ls3d_lod_dist
    del bpy.types.Object.ls3d_sector_flags1
    del bpy.types.Object.ls3d_sector_flags2
    del bpy.types.Object.ls3d_portal_flags
    del bpy.types.Object.ls3d_portal_near
    del bpy.types.Object.ls3d_portal_far
    del bpy.types.Object.ls3d_portal_unknown
    del bpy.types.Object.ls3d_portal_enabled
    del bpy.types.Object.rot_axis
    del bpy.types.Object.rot_mode
    del bpy.types.Object.mirror_color
    del bpy.types.Object.mirror_dist
    del bpy.types.Object.bbox_min
    del bpy.types.Object.bbox_max
    
    bpy.utils.unregister_class(LS3D_OT_AddNode)
    bpy.utils.unregister_class(The4DSPanel)
    bpy.utils.unregister_class(Import4DS)
    bpy.utils.unregister_class(Export4DS)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
if __name__ == "__main__":
    register()