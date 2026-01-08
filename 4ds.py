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
    "author": "Sev3n, Richard01_CZ, Grok 3 AI, Google Gemini 3 Pro Preview, ChatGPT 5.2",
    "version": (0, 0, 1, 'preview' ),
    "blender": (5, 0, 1),
    "location": "File > Import/Export > 4DS Model File",
    "description": "Import and export LS3D .4ds files (Mafia)",
    "category": "Import-Export",
}
# FileVersion consts
VERSION_MAFIA = 29
VERSION_HD2 = 41
VERSION_CHAMELEON = 42

# Frame Types
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

# Visual Types
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

# Material Flags (Full 32-bit map)
MTL_MISC_UNLIT            = 0x00000001 # Bit 0
MTL_ENV_OVERLAY           = 0x00000100 # Bit 8
MTL_ENV_MULTIPLY          = 0x00000200 # Bit 9
MTL_ENV_ADDITIVE          = 0x00000400 # Bit 10
MTL_ENV_DISABLE_TEX       = 0x00000800 # Bit 11
MTL_ENV_PROJECT_Y         = 0x00001000 # Bit 12
MTL_ENV_DETERMINED_Y      = 0x00002000 # Bit 13
MTL_ENV_DETERMINED_Z      = 0x00004000 # Bit 14
MTL_ENV_ADDEFFECT         = 0x00008000 # Bit 15

# High Word Flags (Standard)
MTL_DISABLE_U_TILING      = 0x00010000 # Bit 16
MTL_DISABLE_V_TILING      = 0x00020000 # Bit 17
MTL_DIFFUSETEX            = 0x00040000 # Bit 18
MTL_ENVMAP                = 0x00080000 # Bit 19
MTL_CALCREFLECTTEXY       = 0x00100000 # Bit 20 (Wet Roads)
MTL_PROJECTREFLECTTEXY    = 0x00200000 # Bit 21
MTL_PROJECTREFLECTTEXZ    = 0x00400000 # Bit 22
MTL_MIPMAP                = 0x00800000 # Bit 23
MTL_ALPHA_IN_TEX          = 0x01000000 # Bit 24 (Image Alpha)
MTL_ANIMATED_ALPHA        = 0x02000000 # Bit 25
MTL_ANIMATED_DIFFUSE      = 0x04000000 # Bit 26
MTL_COLORED               = 0x08000000 # Bit 27 (Vertex Color)
MTL_DOUBLESIDED           = 0x10000000 # Bit 28
MTL_COLORKEY              = 0x20000000 # Bit 29
MTL_ALPHA                 = 0x40000000 # Bit 30
MTL_ADDITIVE              = 0x80000000 # Bit 31

class The4DSPanel(bpy.types.Panel):
    bl_label = "4DS Object Properties"
    bl_idname = "OBJECT_PT_4ds"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    
    def draw(self, context):
        obj = context.object
        layout = self.layout
        if not obj: return

        if obj.type == 'MESH':
            layout.prop(obj, "visual_type", text="Mesh Type")
        layout.separator()
        
        # --- RENDER FLAGS ---
        if obj.type == 'MESH':
            box = layout.box()
            box.label(text="Render Flags 1 (Visual)", icon='RESTRICT_RENDER_OFF')
            
            row = box.row()
            row.prop(obj, "render_flags", text="Raw Int")
            
            # Active Checkbox - Top Left
            row = box.row()
            row.prop(obj, "rf1_active")
            box.separator()
            
            # Using grid for flags
            grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
            grid.prop(obj, "rf1_cast_shadow")
            grid.prop(obj, "rf1_receive_shadow")
            grid.prop(obj, "rf1_draw_last")
            grid.prop(obj, "rf1_zbias")
            
            box = layout.box()
            box.label(text="Render Flags 2 (Logic)", icon='MODIFIER')
            row = box.row()
            row.prop(obj, "render_flags2", text="Raw Int")
            
            grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
            grid.prop(obj, "rf2_decal")
            grid.prop(obj, "rf2_stencil")
            grid.prop(obj, "rf2_mirror")
            grid.prop(obj, "rf2_proj")
            grid.prop(obj, "rf2_nofog")

        # --- CULL FLAGS ---
        box = layout.box()
        box.label(text="Culling & Collision", icon='PHYSICS')
        box.prop(obj, "cull_flags", text="Raw Int")
        
        # Visible is separate
        box.prop(obj, "cf_visible")

        # Label above the checkboxes
        box.label(text="Collision Masks:")
        
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        grid.prop(obj, "cf_coll_player")
        grid.prop(obj, "cf_coll_ai")
        grid.prop(obj, "cf_coll_vehicle")
        grid.prop(obj, "cf_coll_camera")
        grid.prop(obj, "cf_coll_proj")
        grid.prop(obj, "cf_coll_item")

        box.prop(obj, "cf_light_int")

        # --- PARAMS ---
        box = layout.box()
        box.label(text="Special Properties")
        box.prop(obj, "ls3d_user_props", text="", icon='TEXT')

        # --- LOD ---
        if obj.type == 'MESH':
            box = layout.box()
            box.label(text="Level-Of-Detail Settings", icon='MESH_DATA')
            box.prop(obj, "ls3d_lod_dist")

        # --- SPECIFIC TYPES ---
        if "plane" in obj.name.lower() or "portal" in obj.name.lower():
            box = layout.box()
            box.label(text="Portal", icon='OUTLINER_OB_LIGHT')
            box.prop(obj, "ls3d_portal_enabled", toggle=True)
            box.prop(obj, "ls3d_portal_flags")
            row = box.row(align=True)
            row.prop(obj, "ls3d_portal_near")
            row.prop(obj, "ls3d_portal_far")

        if obj.type == 'MESH' and "sector" in obj.name.lower():
            box = layout.box()
            box.label(text="Sector", icon='SCENE_DATA')
            box.prop(obj, "ls3d_sector_flags1")
            box.prop(obj, "ls3d_sector_flags2")

        if obj.type == 'MESH' and hasattr(obj, "visual_type") and obj.visual_type == '4':
            box = layout.box()
            box.label(text="Billboard", icon='IMAGE_PLANE')
            box.prop(obj, "rot_mode")
            box.prop(obj, "rot_axis")

        if obj.type == 'MESH' and hasattr(obj, "visual_type") and obj.visual_type == '8':
            box = layout.box()
            box.label(text="Mirror", icon='MOD_MIRROR')
            box.prop(obj, "mirror_color")
            box.prop(obj, "mirror_dist")

def safe_link(tree, from_socket, to_socket):
    if from_socket and to_socket:
        tree.links.new(from_socket, to_socket)

def get_or_create_ls3d_group():
    group_name = "LS3D Material Data"
    
    if group_name in bpy.data.node_groups:
        ng = bpy.data.node_groups[group_name]
        # Cleanup if structure is outdated or has old sockets
        if any(n in s.name for s in ng.interface.items_tree for n in ["Tint", "Key", "Emission", "Environment"]):
            ng.nodes.clear(); ng.interface.clear()
    else:
        ng = bpy.data.node_groups.new(name=group_name, type='ShaderNodeTree')

    # Interface
    if not ng.interface.items_tree:
        # Texture Inputs
        ng.interface.new_socket("Diffuse Map", in_out='INPUT', socket_type='NodeSocketColor')
        ng.interface.new_socket("Alpha Map", in_out='INPUT', socket_type='NodeSocketColor')
        ng.interface.new_socket("Reflection", in_out='INPUT', socket_type='NodeSocketColor')
        
        # Values
        op_socket = ng.interface.new_socket("Opacity", in_out='INPUT', socket_type='NodeSocketFloat')
        
        # Info (Pass-through for scripts/drivers if needed)
        ng.interface.new_socket("Anim Frames", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("Anim Period", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("Env Mode", in_out='INPUT', socket_type='NodeSocketFloat')
        ng.interface.new_socket("Env Type", in_out='INPUT', socket_type='NodeSocketFloat')

        ng.interface.new_socket("BSDF", in_out='OUTPUT', socket_type='NodeSocketShader')

    # Setup Defaults
    for socket in ng.interface.items_tree:
        if socket.bl_socket_idname == 'NodeSocketColor':
            socket.default_value = (1.0, 1.0, 1.0, 1.0)
            if "Reflection" in socket.name: 
                socket.default_value = (0.0, 0.0, 0.0, 1.0)
        elif socket.bl_socket_idname == 'NodeSocketFloat':
            socket.default_value = 0.0
            if "Opacity" in socket.name: 
                socket.default_value = 100.0
                socket.min_value = 0.0
                socket.max_value = 100.0
            if "Env Mode" in socket.name: socket.default_value = 2.0 

    # Nodes Construction
    if not ng.nodes:
        input_node = ng.nodes.new('NodeGroupInput')
        input_node.location = (-1000, 0)
        output_node = ng.nodes.new('NodeGroupOutput')
        output_node.location = (600, 0)
        
        # 1. Add Environment/Reflection (Diffuse + Reflection)
        # Note: We removed Diffuse Tint multiplication. Diffuse Map goes straight here.
        add_env = ng.nodes.new('ShaderNodeMixRGB')
        add_env.blend_type = 'ADD'
        add_env.inputs['Fac'].default_value = 1.0
        add_env.location = (-700, 200)

        # 2. Opacity Logic (0-100 -> 0-1)
        math_op_scale = ng.nodes.new('ShaderNodeMath')
        math_op_scale.operation = 'DIVIDE'
        math_op_scale.inputs[1].default_value = 100.0
        math_op_scale.location = (-900, -100)

        # 3. Alpha Logic (Opacity * Alpha Map)
        math_alpha = ng.nodes.new('ShaderNodeMath')
        math_alpha.operation = 'MULTIPLY'
        math_alpha.location = (-700, -100)

        # 4. Shader
        principled = ng.nodes.new('ShaderNodeBsdfPrincipled')
        principled.location = (0, 200)
        # Matte base. Reflections are added via Texture input, not PBR specular.
        principled.inputs["Roughness"].default_value = 1.0 
        principled.inputs["Specular IOR Level"].default_value = 0.0
        principled.inputs["Metallic"].default_value = 0.0
        principled.inputs["Emission Color"].default_value = (0,0,0,1) # No input, default to black
        
        emission = ng.nodes.new('ShaderNodeEmission')
        emission.location = (0, -100)
        
        # Wiring
        inputs = input_node.outputs
        
        # Diffuse & Reflection
        safe_link(ng, inputs.get("Diffuse Map"), add_env.inputs[1])
        safe_link(ng, inputs.get("Reflection"), add_env.inputs[2])
        
        # Opacity Scaling
        safe_link(ng, inputs.get("Opacity"), math_op_scale.inputs[0])
        
        # Alpha Calculation
        safe_link(ng, math_op_scale.outputs[0], math_alpha.inputs[0])
        safe_link(ng, inputs.get("Alpha Map"), math_alpha.inputs[1])
        
        # Shader Inputs
        safe_link(ng, add_env.outputs[0], principled.inputs["Base Color"])
        
        # Alpha Connection
        safe_link(ng, math_alpha.outputs[0], principled.inputs["Alpha"]) 
        
        # Emission (Alternative flow)
        safe_link(ng, add_env.outputs[0], emission.inputs["Color"])
        safe_link(ng, math_alpha.outputs[0], emission.inputs["Strength"])
        
        # OUTPUT
        safe_link(ng, principled.outputs[0], output_node.inputs["BSDF"])
    
    return ng

class LS3D_OT_AddEnvSetup(bpy.types.Operator):
    """Add Reflection Texture Setup"""
    bl_idname = "node.add_ls3d_env_setup"
    bl_label = "Add Reflection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat = context.object.active_material
        if not mat or not mat.use_nodes: return {'CANCELLED'}
        
        tree = mat.node_tree
        nodes = tree.nodes
        links = tree.links
        
        ls3d_node = next((n for n in nodes if n.type == 'GROUP' and n.node_tree and "LS3D Material Data" in n.node_tree.name), None)
        if not ls3d_node: return {'CANCELLED'}

        # 1. Frame
        frame = nodes.new('NodeFrame')
        frame.label = "Reflection"
        frame.location = (-600, -400)
        
        # 2. Nodes
        coord = nodes.new('ShaderNodeTexCoord')
        coord.location = (-1100, -400); coord.parent = frame
        
        mapping = nodes.new('ShaderNodeMapping')
        mapping.vector_type = 'TEXTURE'
        mapping.location = (-900, -400); mapping.parent = frame
        
        tex_image = nodes.new('ShaderNodeTexImage')
        tex_image.location = (-700, -400); tex_image.parent = frame
        tex_image.label = "Reflection Map"
        tex_image.projection = 'SPHERE' 
        
        env_group_data = get_or_create_env_group()
        env_group = nodes.new('ShaderNodeGroup')
        env_group.node_tree = env_group_data
        env_group.location = (-400, -400); env_group.parent = frame
        
        # 3. Wiring
        links.new(coord.outputs["Reflection"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], tex_image.inputs["Vector"])
        links.new(tex_image.outputs["Color"], env_group.inputs["Color"])
        links.new(env_group.outputs["Output"], ls3d_node.inputs["Reflection"])
        
        # Toggle property instead of node socket
        mat.ls3d_env_enabled = True
        
        return {'FINISHED'}
                    
def get_or_create_env_group():
    group_name = "LS3D Environment"
    
    if group_name in bpy.data.node_groups:
        return bpy.data.node_groups[group_name]
    
    ng = bpy.data.node_groups.new(name=group_name, type='ShaderNodeTree')
    
    # Interface
    ng.interface.new_socket("Color", in_out='INPUT', socket_type='NodeSocketColor')
    ng.interface.new_socket("Intensity", in_out='INPUT', socket_type='NodeSocketFloat')
    ng.interface.new_socket("Output", in_out='OUTPUT', socket_type='NodeSocketColor')
    
    # Default values
    if "Intensity" in ng.interface.items_tree:
        ng.interface.items_tree["Intensity"].default_value = 1.0
        ng.interface.items_tree["Intensity"].min_value = 0.0
        ng.interface.items_tree["Intensity"].max_value = 100.0 # Clamp max
    
    # Nodes
    input_node = ng.nodes.new('NodeGroupInput')
    input_node.location = (-300, 0)
    
    output_node = ng.nodes.new('NodeGroupOutput')
    output_node.location = (300, 0)
    
    mix = ng.nodes.new('ShaderNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Fac'].default_value = 1.0
    mix.location = (0, 0)
    
    # Links
    ng.links.new(input_node.outputs["Color"], mix.inputs[1])
    ng.links.new(input_node.outputs["Intensity"], mix.inputs[2])
    ng.links.new(mix.outputs[0], output_node.inputs["Output"])
    
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
        """Recursively find an Image Texture node."""
        if not node:
            return None
            
        # Case A: It is an Image Node
        if node.type == 'TEX_IMAGE':
            return node
            
        # Case B: It is a Node Group (Dig inside)
        if node.type == 'GROUP' and node.node_tree:
            # Look for the specific texture node inside the group
            # We prioritize nodes labeled "Env Texture" or just the first image node found
            for inner_node in node.node_tree.nodes:
                if inner_node.type == 'TEX_IMAGE':
                    return inner_node
        
        # Case C: Pass-through nodes (Mix, Math, etc)
        if hasattr(node, "inputs"):
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
        # 1. Colors & Opacity
        env_color = getattr(mat, "ls3d_ambient_color", (0.5, 0.5, 0.5))
        diffuse_color = getattr(mat, "ls3d_diffuse_color", (1.0, 1.0, 1.0))
        emission_color = getattr(mat, "ls3d_emission_color", (0.0, 0.0, 0.0))
        
        opacity = 1.0
        if mat.use_nodes and mat.node_tree:
            ls3d_node = next((n for n in mat.node_tree.nodes if n.type == 'GROUP' and n.node_tree and "LS3D Material Data" in n.node_tree.name), None)
            if ls3d_node and "Opacity" in ls3d_node.inputs:
                opacity = ls3d_node.inputs["Opacity"].default_value / 100.0

        # 2. BUILD FLAGS (Using Constants)
        final_flags = 0
        
        # High Word / Standard
        if not mat.ls3d_misc_tile_u:  final_flags |= MTL_DISABLE_U_TILING
        if not mat.ls3d_misc_tile_v:  final_flags |= MTL_DISABLE_V_TILING
        if mat.ls3d_diff_enabled:     final_flags |= MTL_DIFFUSETEX
        if mat.ls3d_env_enabled:      final_flags |= MTL_ENVMAP
        if mat.ls3d_calc_reflect_y:   final_flags |= MTL_CALCREFLECTTEXY
        if mat.ls3d_proj_reflect_y:   final_flags |= MTL_PROJECTREFLECTTEXY
        if mat.ls3d_proj_reflect_z:   final_flags |= MTL_PROJECTREFLECTTEXZ
        if mat.ls3d_diff_mipmap:      final_flags |= MTL_MIPMAP
        if mat.ls3d_alpha_imgalpha:   final_flags |= MTL_ALPHA_IN_TEX
        if mat.ls3d_alpha_anim:       final_flags |= MTL_ANIMATED_ALPHA
        if mat.ls3d_diff_anim:        final_flags |= MTL_ANIMATED_DIFFUSE
        if mat.ls3d_diff_colored:     final_flags |= MTL_COLORED
        if mat.ls3d_diff_2sided:      final_flags |= MTL_DOUBLESIDED
        if mat.ls3d_alpha_colorkey:   final_flags |= MTL_COLORKEY
        if mat.ls3d_alpha_enabled:    final_flags |= MTL_ALPHA
        if mat.ls3d_alpha_addmix:     final_flags |= MTL_ADDITIVE
        if mat.ls3d_misc_zwrite:      final_flags |= MTL_ADDITIVE # Fallback for Z-Write

        # Environment Byte
        if mat.ls3d_env_overlay:      final_flags |= MTL_ENV_OVERLAY
        if mat.ls3d_env_multiply:     final_flags |= MTL_ENV_MULTIPLY
        if mat.ls3d_env_additive:     final_flags |= MTL_ENV_ADDITIVE
        if mat.ls3d_disable_tex:      final_flags |= MTL_ENV_DISABLE_TEX
        if mat.ls3d_env_yproj:        final_flags |= MTL_ENV_PROJECT_Y
        if mat.ls3d_env_ydet:         final_flags |= MTL_ENV_DETERMINED_Y
        if mat.ls3d_env_zdet:         final_flags |= MTL_ENV_DETERMINED_Z
        if mat.ls3d_alpha_effect:     final_flags |= MTL_ENV_ADDEFFECT

        # Misc Byte
        if mat.ls3d_misc_unlit:       final_flags |= MTL_MISC_UNLIT

        # 3. WRITE DATA
        f.write(struct.pack("<I", final_flags))
        f.write(struct.pack("<3f", *env_color))
        f.write(struct.pack("<3f", *diffuse_color))
        f.write(struct.pack("<3f", *emission_color))
        f.write(struct.pack("<f", opacity))

        # 4. TEXTURE NODES
        env_opacity = 0.0
        env_tex = ""
        diffuse_tex = ""
        alpha_tex = ""

        if mat.use_nodes and mat.node_tree:
             nodes = mat.node_tree.nodes
             ls3d_node = next((n for n in nodes if n.type == 'GROUP' and n.node_tree and "LS3D Material Data" in n.node_tree.name), None)
             
             if ls3d_node:
                 if "Diffuse Map" in ls3d_node.inputs and ls3d_node.inputs["Diffuse Map"].is_linked:
                     tex = self.find_texture_node(ls3d_node.inputs["Diffuse Map"].links[0].from_node)
                     if tex and tex.image: diffuse_tex = os.path.basename(tex.image.filepath or tex.image.name)
                 
                 if mat.ls3d_alpha_enabled and "Alpha Map" in ls3d_node.inputs and ls3d_node.inputs["Alpha Map"].is_linked:
                     tex = self.find_texture_node(ls3d_node.inputs["Alpha Map"].links[0].from_node)
                     if tex and tex.image: alpha_tex = os.path.basename(tex.image.filepath or tex.image.name)
                 
                 if mat.ls3d_env_enabled and "Reflection" in ls3d_node.inputs and ls3d_node.inputs["Reflection"].is_linked:
                     link_node = ls3d_node.inputs["Reflection"].links[0].from_node
                     if link_node.type == 'GROUP' and link_node.node_tree and "LS3D Environment" in link_node.node_tree.name:
                         if "Intensity" in link_node.inputs: env_opacity = link_node.inputs["Intensity"].default_value
                         if link_node.inputs["Color"].is_linked:
                             tex = self.find_texture_node(link_node.inputs["Color"].links[0].from_node)
                             if tex and tex.image: env_tex = os.path.basename(tex.image.filepath or tex.image.name)
                     else:
                         tex = self.find_texture_node(link_node)
                         if tex and tex.image: 
                             env_tex = os.path.basename(tex.image.filepath or tex.image.name); env_opacity = 1.0

        if mat.ls3d_env_enabled:
            f.write(struct.pack("<f", env_opacity))
            self.write_string(f, env_tex.upper())
        self.write_string(f, diffuse_tex.upper())
        if mat.ls3d_alpha_enabled:
            self.write_string(f, alpha_tex.upper())
            
        if mat.ls3d_diff_anim:
            f.write(struct.pack("<I", mat.ls3d_diff_frame_count))
            f.write(struct.pack("<H", 0))
            f.write(struct.pack("<I", mat.ls3d_diff_frame_period))
            f.write(struct.pack("<I", 0))
            f.write(struct.pack("<I", 0))

    def serialize_object(self, f, obj, lods):
        f.write(struct.pack("<H", 0))
        f.write(struct.pack("<B", len(lods)))
        
        # Initialize storage to prevent crash
        self.current_lod_mappings = [] 
        self.current_lod_counts = []
        
        # Helper: Quantization for vertex deduplication (5 decimals)
        def quant(val):
            if abs(val) < 0.00001: val = 0.0
            return int(val * 100000.0)

        for lod_idx, lod_obj in enumerate(lods):
            # --- 1. HANDLE FADE DISTANCE ---
            # STRICTLY READ FROM UI: No auto-correction, no forcing LOD0 to 0.
            # We trust the user has set the correct value in the panel.
            dist = getattr(lod_obj, "ls3d_lod_dist", 0.0)
            
            f.write(struct.pack("<f", float(dist)))
            
            # --- 2. MESH PROCESSING ---
            try:
                # Blender 5.0 safe evaluation
                depsgraph = bpy.context.evaluated_depsgraph_get()
                eval_obj = lod_obj.evaluated_get(depsgraph)
                temp_mesh = eval_obj.to_mesh()
            except:
                temp_mesh = lod_obj.data.copy()

            # Triangulate
            bm = bmesh.new()
            bm.from_mesh(temp_mesh)
            bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
            bm.to_mesh(temp_mesh)
            bm.free()
            
            # Access Data Layers
            uv_layer = temp_mesh.uv_layers.active.data if temp_mesh.uv_layers.active else None
            unique_verts = {}
            final_verts = []
            mat_groups = {}
            vert_map = {} 
            
            # Ensure normals are ready
            try: temp_mesh.calc_normals_split()
            except: pass
            
            for poly in temp_mesh.polygons:
                f_indices = []
                for loop_index in poly.loop_indices:
                    loop = temp_mesh.loops[loop_index]
                    v_index = loop.vertex_index
                    v_co = temp_mesh.vertices[v_index].co
                    
                    u, v_coord = (0.0, 0.0)
                    if uv_layer:
                        d = uv_layer[loop_index].uv
                        u, v_coord = d[0], 1.0 - d[1]
                    
                    norm = loop.normal
                    
                    # Deduplication Key
                    key = (
                        quant(v_co.x), quant(v_co.y), quant(v_co.z),
                        quant(norm.x), quant(norm.y), quant(norm.z),
                        quant(u), quant(v_coord)
                    )
                    
                    if key in unique_verts:
                        idx = unique_verts[key]
                    else:
                        idx = len(final_verts)
                        unique_verts[key] = idx
                        final_verts.append({
                            'pos': (v_co.x, v_co.z, v_co.y),
                            'norm': (norm.x, norm.z, norm.y),
                            'uv': (u, v_coord)
                        })
                    
                    # Map for skinning
                    if v_index not in vert_map: vert_map[v_index] = []
                    if idx not in vert_map[v_index]: vert_map[v_index].append(idx)
                    
                    f_indices.append(idx)
                
                mat_groups.setdefault(poly.material_index, []).append(f_indices)
            
            lod_obj.to_mesh_clear()
            
            self.current_lod_mappings.append(vert_map)
            self.current_lod_counts.append(len(final_verts))

            # --- 3. WRITE DATA ---
            f.write(struct.pack("<H", len(final_verts)))
            for v in final_verts:
                f.write(struct.pack("<3f", *v['pos']))
                f.write(struct.pack("<3f", *v['norm']))
                f.write(struct.pack("<2f", *v['uv']))
            
            f.write(struct.pack("<B", len(mat_groups)))
            for mat_idx, faces in mat_groups.items():
                f.write(struct.pack("<H", len(faces)))
                for tri in faces:
                    if len(tri) == 3:
                        f.write(struct.pack("<3H", tri[0], tri[2], tri[1]))
                
                mat_id = 0
                if mat_idx < len(lod_obj.material_slots):
                    real_mat = lod_obj.material_slots[mat_idx].material
                    if real_mat in self.materials:
                        mat_id = self.materials.index(real_mat) + 1
                f.write(struct.pack("<H", mat_id))
            
        return len(lods)
    
    def serialize_frame(self, f, obj):
        frame_type = FRAME_VISUAL
        visual_type = VISUAL_OBJECT
        
        r_flag1 = getattr(obj, "render_flags", 128)
        r_flag2 = getattr(obj, "render_flags2", 42)
        visual_flags = (r_flag1, r_flag2)
        
        if obj.type == "MESH":
            if hasattr(obj, "visual_type"):
                visual_type = int(obj.visual_type)
                if visual_type in (VISUAL_SINGLEMESH, VISUAL_SINGLEMORPH):
                    has_arm = any(m.type == 'ARMATURE' and m.object for m in obj.modifiers)
                    if not has_arm: visual_type = VISUAL_OBJECT
            else:
                if obj.modifiers and any(mod.type == "ARMATURE" for mod in obj.modifiers):
                    visual_type = VISUAL_SINGLEMORPH if obj.data.shape_keys else VISUAL_SINGLEMESH
                elif "portal" in obj.name.lower(): pass 
                elif "sector" in obj.name.lower(): frame_type = FRAME_SECTOR
                elif obj.display_type == "WIRE": frame_type = FRAME_OCCLUDER
                elif obj.data.shape_keys: visual_type = VISUAL_MORPH
        
        elif obj.type == "EMPTY":
            if obj.empty_display_type == "CUBE": frame_type = FRAME_DUMMY
            elif obj.empty_display_type == "PLAIN_AXES": frame_type = FRAME_TARGET
        
        parent_id = 0
        if obj.parent:
            if obj.parent_type == 'BONE' and obj.parent_bone:
                parent_id = self.joint_map.get(obj.parent_bone, 0)
            elif obj.parent in self.frames_map:
                parent_id = self.frames_map[obj.parent]
        
        self.frames_map[obj] = self.frame_index
        self.frame_index += 1
        
        if obj.parent and obj.parent_type != 'BONE':
             matrix = obj.parent.matrix_world.inverted() @ obj.matrix_world
        elif obj.parent and obj.parent_type == 'BONE':
             arm = obj.parent
             bone = arm.data.bones[obj.parent_bone]
             bone_world = arm.matrix_world @ bone.matrix_local
             matrix = bone_world.inverted() @ obj.matrix_world
        else:
             matrix = obj.matrix_world
             
        pos = matrix.to_translation()
        rot = matrix.to_quaternion()
        scale = matrix.to_scale()
        
        f.write(struct.pack("<B", frame_type))
        if frame_type == FRAME_VISUAL:
            f.write(struct.pack("<B", visual_type))
            f.write(struct.pack("<2B", *visual_flags))
            
        f.write(struct.pack("<H", parent_id))
        f.write(struct.pack("<3f", pos.x, pos.z, pos.y))
        f.write(struct.pack("<3f", scale.x, scale.z, scale.y))
        f.write(struct.pack("<4f", rot.w, rot.x, rot.z, rot.y))
        f.write(struct.pack("<B", getattr(obj, "cull_flags", 128)))
        self.write_string(f, obj.name)
        self.write_string(f, getattr(obj, "ls3d_user_props", ""))
        
        if frame_type == FRAME_VISUAL:
            lods = self.lod_map.get(obj, [obj])
            num = self.serialize_object(f, obj, lods)
            
            if visual_type == VISUAL_BILLBOARD:
                self.serialize_billboard(f, obj)
            elif visual_type == VISUAL_MIRROR:
                self.serialize_mirror(f, obj)
            elif visual_type == VISUAL_SINGLEMESH:
                self.serialize_singlemesh(f, obj, num)
            elif visual_type == VISUAL_SINGLEMORPH:
                self.serialize_singlemesh(f, obj, num)
                self.serialize_morph(f, obj, num)
            elif visual_type == VISUAL_MORPH:
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
        # We don't write the Armature Object itself as a frame, 
        # but we need to pass its hierarchy context.
        # Parent ID for the root bone is the Armature's parent (if any).
        
        arm_parent_id = 0
        if armature.parent:
             arm_parent_id = self.frames_map.get(armature.parent, 0)
        
        # Iterate bones
        for bone in armature.data.bones:
            frame_type = FRAME_JOINT
            
            # Determine Parent ID
            if bone.parent:
                parent_id = self.joint_map.get(bone.parent.name, 0)
            else:
                # Root bone connects to Armature's parent
                parent_id = arm_parent_id
            
            # Register this bone
            self.joint_map[bone.name] = self.frame_index
            self.frame_index += 1
            
            # Calculate Transform
            if bone.parent:
                matrix = bone.parent.matrix_local.inverted() @ bone.matrix_local
            else:
                matrix = bone.matrix_local
            
            pos = matrix.to_translation()
            rot = matrix.to_quaternion()
            scale = matrix.to_scale()
            
            f.write(struct.pack("<B", frame_type))
            f.write(struct.pack("<H", parent_id))
            f.write(struct.pack("<3f", pos.x, pos.z, pos.y))
            f.write(struct.pack("<3f", scale.x, scale.z, scale.y))
            f.write(struct.pack("<4f", rot.w, rot.x, rot.z, rot.y))
            f.write(struct.pack("<B", 0)) # Joint flags (unused?)
            self.write_string(f, bone.name)
            self.write_string(f, "") # User props
            
            # Joint Body
            self.serialize_joint(f, bone, armature, parent_id)
            
    def collect_lods(self):
        self.lod_map = {}
        all_lod_objects = set()
        
        base_objects = [o for o in self.objects_to_export if o.type == "MESH" and "_lod" not in o.name]
        scene_objects = bpy.context.scene.objects
        
        for base_obj in base_objects:
            self.lod_map[base_obj] = [base_obj]
            base_name = base_obj.name
            
            for i in range(1, 10): 
                target_name = f"{base_name}_lod{i}"
                
                if target_name in scene_objects:
                    found_lod = scene_objects[target_name]
                    if found_lod.type == "MESH":
                        while len(self.lod_map[base_obj]) <= i:
                            self.lod_map[base_obj].append(None)
                        
                        self.lod_map[base_obj][i] = found_lod
                        all_lod_objects.add(found_lod)
            
            self.lod_map[base_obj] = [x for x in self.lod_map[base_obj] if x is not None]

        return all_lod_objects
    
    def serialize_file(self):
        with open(self.filepath, "wb") as f:
            self.serialize_header(f)
            
            self.materials = self.collect_materials()
            f.write(struct.pack("<H", len(self.materials)))
            for i, mat in enumerate(self.materials):
                self.serialize_material(f, mat, i + 1)
            
            lod_objects_set = self.collect_lods()
            
            # SAFE CHECK: Use object names to check existence in scene
            scene_names = set(o.name for o in bpy.context.scene.objects)
            
            raw_objects = [
                obj for obj in self.objects_to_export
                if obj.name in scene_names 
                and obj not in lod_objects_set
                and obj.type in ("MESH", "EMPTY", "ARMATURE")
            ]
            
            # HIERARCHY SORT
            self.objects = []
            roots = [o for o in raw_objects if (not o.parent) or (o.parent not in raw_objects)]
            roots.sort(key=lambda x: x.name)

            def sort_hierarchy(obj):
                if obj in self.objects: return 
                self.objects.append(obj)
                children = [c for c in obj.children if c in raw_objects]
                children.sort(key=lambda x: x.name)
                for child in children:
                    sort_hierarchy(child)

            for root in roots:
                sort_hierarchy(root)
            
            seen = set(self.objects)
            leftovers = [o for o in raw_objects if o not in seen]
            self.objects.extend(leftovers)

            armatures = [obj for obj in self.objects if obj.type == "ARMATURE"]
            visual_frames = [obj for obj in self.objects if obj.type != "ARMATURE"]
            
            bone_count = sum(len(arm.data.bones) for arm in armatures)
            total_frames = len(visual_frames) + bone_count
            
            f.write(struct.pack("<H", total_frames))
            
            self.frame_index = 1
            self.frames_map = {} 
            self.joint_map = {}
            
            for obj in self.objects:
                if obj.type == "ARMATURE":
                    self.serialize_joints(f, obj)
                else:
                    self.serialize_frame(f, obj)
                
            f.write(struct.pack("<?", False))

class The4DSPanelMaterial(bpy.types.Panel):
    bl_label = "4DS Material Properties"
    bl_idname = "MATERIAL_PT_4ds"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    
    def draw(self, context):
        mat = context.material
        if not mat: return
        layout = self.layout
        
        # 2. Colors
        box = layout.box()
        box.label(text="-Colors-", icon='COLOR')
        col = box.column(align=True)
        col.prop(mat, "ls3d_diffuse_color", text="Diffuse")
        col.prop(mat, "ls3d_ambient_color", text="Environment")
        col.prop(mat, "ls3d_emission_color", text="Emission")
        
        # 3. Textures
        layout.label(text="-Textures-", icon='TEXTURE')
        
        # A. Diffuse
        box = layout.box()
        box.label(text="Diffuse", icon='SHADING_TEXTURE')
        box.prop(mat, "ls3d_diff_enabled")
        
        col = box.column(align=True)
        r = col.row()
        r.prop(mat, "ls3d_diff_colored")
        r.prop(mat, "ls3d_diff_anim")
            
        r = col.row()
        r.prop(mat, "ls3d_diff_mipmap")
        r.prop(mat, "ls3d_diff_2sided")

        if mat.ls3d_diff_anim:
            r = col.row(align=True)
            r.prop(mat, "ls3d_diff_frame_count")
            r.prop(mat, "ls3d_diff_frame_period")
        
        # B. Environment
        box = layout.box()
        box.label(text="Environment", icon='WORLD_DATA')
        box.prop(mat, "ls3d_env_enabled")
        
        col = box.column(align=True)
        r = col.row()
        r.prop(mat, "ls3d_env_overlay")
        r.prop(mat, "ls3d_env_multiply")
        r.prop(mat, "ls3d_env_additive")
        
        r = col.row()
        r.prop(mat, "ls3d_env_yproj")
        r.prop(mat, "ls3d_env_ydet")
        r.prop(mat, "ls3d_env_zdet")
        
        if mat.ls3d_env_enabled:
            box.separator()
            box.operator("node.add_ls3d_env_setup", icon='NODETREE', text="Add Reflection Nodes")
        
        # C. Alpha
        box = layout.box()
        box.label(text="Alpha", icon='TRIA_RIGHT')
        box.prop(mat, "ls3d_alpha_enabled")
        
        col = box.column(align=True)
        r = col.row()
        r.prop(mat, "ls3d_alpha_effect")
        r.prop(mat, "ls3d_alpha_colorkey")
        
        r = col.row()
        r.prop(mat, "ls3d_alpha_addmix")
        r.prop(mat, "ls3d_alpha_anim")
        
        col.prop(mat, "ls3d_alpha_imgalpha")
        
        # D. Misc / Reflection Calc
        box = layout.box()
        box.label(text="Misc / Unknown")
        col = box.column(align=True)
        
        col.prop(mat, "ls3d_disable_tex")
        col.separator()
        col.prop(mat, "ls3d_misc_unlit")
        col.prop(mat, "ls3d_misc_zwrite")
        
        r = col.row()
        r.prop(mat, "ls3d_misc_tile_u")
        r.prop(mat, "ls3d_misc_tile_v")
        
        # Renamed properties used here (previously unk_12/13/14)
        r = col.row()
        r.prop(mat, "ls3d_calc_reflect_y")
        r.prop(mat, "ls3d_proj_reflect_y")
        r.prop(mat, "ls3d_proj_reflect_z")

        # Master Node Button
        layout.separator()
        layout.operator("node.add_ls3d_group", icon='NODETREE', text="Add LS3D Material Data Node")

class The4DSImporter:
    def __init__(self, filepath):
        self.filepath = filepath
        self.texture_cache = {}
        
        # 1. Determine Paths
        # E.g. filepath = "D:\Mafia\models\car.4ds"
        model_dir = os.path.dirname(filepath)
        
        # FIX: Go back ONE level (models -> Mafia), not two
        self.base_dir = os.path.abspath(os.path.join(model_dir, ".."))
        print(f"Base directory set to: {self.base_dir}")
        
        self.maps_dir = None
        
        # Helper to find folder case-insensitively
        def find_folder(base, target_name):
            if not os.path.exists(base): return None
            try:
                for name in os.listdir(base):
                    if name.lower() == target_name.lower() and os.path.isdir(os.path.join(base, name)):
                        return os.path.join(base, name)
            except OSError:
                pass
            return None

        # 1. Look for 'maps' in the parent directory (Standard Mafia structure)
        self.maps_dir = find_folder(self.base_dir, "maps")
        
        # 2. Fallback: Look for 'maps' in the same directory as the model
        if not self.maps_dir:
            self.maps_dir = find_folder(model_dir, "maps")
            
        if self.maps_dir:
            print(f"Maps directory found at: {self.maps_dir}")
        else:
            # Keep original warning message style
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

    def get_real_file_path(self, directory, filename):
        """Finds a file in a directory case-insensitively."""
        if not directory or not os.path.exists(directory):
            return None
            
        # Fast path: exact match
        exact_path = os.path.join(directory, filename)
        if os.path.exists(exact_path):
            return exact_path
            
        # Slow path: iterate directory
        filename_lower = filename.lower()
        try:
            for name in os.listdir(directory):
                if name.lower() == filename_lower:
                    return os.path.join(directory, name)
        except OSError:
            pass
            
        return None

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
    
    def get_color_key(self, filename):
        """
        Reads Index 0 from BMP palette (Offset 54).
        Returns linear RGB tuple.
        """
        if not self.maps_dir:
            return None
            
        # Clean filename just in case a path was passed
        base_name = os.path.basename(filename)
        full_path = self.get_real_file_path(self.maps_dir, base_name)
        
        if not full_path:
            return None
            
        try:
            with open(full_path, "rb") as f:
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
            print(f"Error reading Color Key from {full_path}: {e}")
            
        return None
            
    def get_or_load_texture(self, filename):
        # Normalize cache key
        base_name = os.path.basename(filename)
        norm_key = base_name.lower()
        
        if norm_key not in self.texture_cache:
            full_path = None
            
            if self.maps_dir:
                full_path = self.get_real_file_path(self.maps_dir, base_name)
            
            if full_path:
                try:
                    image = bpy.data.images.load(full_path, check_existing=True)
                    self.texture_cache[norm_key] = image
                except Exception as e:
                    print(f"Warning: Failed to load texture {full_path}: {e}")
                    self.texture_cache[norm_key] = None
            else:
                # Keep original warning style, but specific to filename
                print(f"Warning: Texture file not found: {os.path.join(self.base_dir, 'maps', base_name)}")
                self.texture_cache[norm_key] = None
                
        return self.texture_cache[norm_key]
    
    def set_material_data(
        self, material, diffuse, alpha_tex, env_tex, emission, alpha, metallic, use_color_key
    ):
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        nodes.clear()
        
        principled = nodes.new("ShaderNodeBsdfPrincipled")
        principled.location = (0, 0)
        principled.inputs["Emission Color"].default_value = (*emission, 1.0)
        principled.inputs["Metallic"].default_value = 0.0
        principled.inputs["Specular IOR Level"].default_value = 0.0
        principled.inputs["Roughness"].default_value = 1.0
        
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 0)
        
        base_color_input = principled.inputs["Base Color"]
        
        # Diffuse Texture
        if diffuse:
            diffuse = diffuse.lower()
            tex_image = nodes.new("ShaderNodeTexImage")
            tex_image.image = self.get_or_load_texture(diffuse)
            tex_image.location = (-300, 0)
         
            if tex_image.image:
                links.new(tex_image.outputs["Color"], principled.inputs["Base Color"])
            
            # Color Key (Alpha Clip)
            if use_color_key:
                color_key = self.get_color_key(os.path.join(self.base_dir, "maps", diffuse))
                if color_key:
                    normalized_sum = color_key[0] + color_key[1] + color_key[2]
                    threshold_value = 0.3 if diffuse == "2kolo3.bmp" else 0.015 + 0.45 * normalized_sum
                    
                    separate_rgb = nodes.new("ShaderNodeSeparateColor")
                    separate_rgb.location = (-100, 200)
                    links.new(tex_image.outputs["Color"], separate_rgb.inputs["Color"])
                    
                    math_r = nodes.new("ShaderNodeMath"); math_r.operation = "SUBTRACT"; math_r.inputs[0].default_value = color_key[0]
                    links.new(separate_rgb.outputs["Red"], math_r.inputs[1])
                    
                    math_g = nodes.new("ShaderNodeMath"); math_g.operation = "SUBTRACT"; math_g.inputs[0].default_value = color_key[1]
                    links.new(separate_rgb.outputs["Green"], math_g.inputs[1])
                    
                    math_b = nodes.new("ShaderNodeMath"); math_b.operation = "SUBTRACT"; math_b.inputs[0].default_value = color_key[2]
                    links.new(separate_rgb.outputs["Blue"], math_b.inputs[1])
                    
                    add_rg = nodes.new("ShaderNodeMath"); add_rg.operation = "ADD"
                    links.new(math_r.outputs["Value"], add_rg.inputs[0])
                    links.new(math_g.outputs["Value"], add_rg.inputs[1])
                    
                    add_rgb = nodes.new("ShaderNodeMath"); add_rgb.operation = "ADD"
                    links.new(add_rg.outputs["Value"], add_rgb.inputs[0])
                    links.new(math_b.outputs["Value"], add_rgb.inputs[1])
                    
                    threshold = nodes.new("ShaderNodeMath"); threshold.operation = "GREATER_THAN" # Inverted logic for Alpha input
                    threshold.inputs[1].default_value = threshold_value
                    links.new(add_rgb.outputs["Value"], threshold.inputs[0])
                    
                    # Connect to Alpha directly
                    links.new(threshold.outputs["Value"], principled.inputs["Alpha"])
                    material.blend_method = "CLIP"
        
        # Alpha Texture
        if alpha_tex:
            alpha_tex = alpha_tex.lower()
            alpha_tex_image = nodes.new("ShaderNodeTexImage")
            alpha_tex_image.image = self.get_or_load_texture(alpha_tex)
            alpha_tex_image.location = (-300, -300)
            if alpha_tex_image.image:
                links.new(alpha_tex_image.outputs["Color"], principled.inputs["Alpha"])
                material.blend_method = "BLEND"
        
        # Environment Texture
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

        # Final Link
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

        # 1. READ RAW FLAGS
        raw_flags = struct.unpack("<I", f.read(4))[0]
        
        # 2. READ VALUES
        mat.ls3d_ambient_color = struct.unpack("<3f", f.read(12))
        mat.ls3d_diffuse_color = struct.unpack("<3f", f.read(12))
        mat.ls3d_emission_color = struct.unpack("<3f", f.read(12))
        opacity = struct.unpack("<f", f.read(4))[0]

        # 3. PARSE FLAGS USING CONSTANTS
        # Tiling is inverted (Flag set = Disable Tiling)
        mat.ls3d_misc_tile_u = not bool(raw_flags & MTL_DISABLE_U_TILING)
        mat.ls3d_misc_tile_v = not bool(raw_flags & MTL_DISABLE_V_TILING)
        
        # Standard
        mat.ls3d_diff_enabled = bool(raw_flags & MTL_DIFFUSETEX)
        mat.ls3d_env_enabled = bool(raw_flags & MTL_ENVMAP)
        mat.ls3d_diff_mipmap = bool(raw_flags & MTL_MIPMAP)
        mat.ls3d_alpha_imgalpha = bool(raw_flags & MTL_ALPHA_IN_TEX)
        mat.ls3d_alpha_anim = bool(raw_flags & MTL_ANIMATED_ALPHA)
        mat.ls3d_diff_anim = bool(raw_flags & MTL_ANIMATED_DIFFUSE)
        mat.ls3d_diff_colored = bool(raw_flags & MTL_COLORED)
        mat.ls3d_diff_2sided = bool(raw_flags & MTL_DOUBLESIDED)
        mat.ls3d_alpha_colorkey = bool(raw_flags & MTL_COLORKEY)
        mat.ls3d_alpha_enabled = bool(raw_flags & MTL_ALPHA)
        mat.ls3d_alpha_addmix = bool(raw_flags & MTL_ADDITIVE)
        
        # Reflection / Advanced
        mat.ls3d_calc_reflect_y = bool(raw_flags & MTL_CALCREFLECTTEXY)
        mat.ls3d_proj_reflect_y = bool(raw_flags & MTL_PROJECTREFLECTTEXY)
        mat.ls3d_proj_reflect_z = bool(raw_flags & MTL_PROJECTREFLECTTEXZ)

        # Environment
        mat.ls3d_env_overlay = bool(raw_flags & MTL_ENV_OVERLAY)
        mat.ls3d_env_multiply = bool(raw_flags & MTL_ENV_MULTIPLY)
        mat.ls3d_env_additive = bool(raw_flags & MTL_ENV_ADDITIVE)
        mat.ls3d_disable_tex = bool(raw_flags & MTL_ENV_DISABLE_TEX)
        mat.ls3d_env_yproj = bool(raw_flags & MTL_ENV_PROJECT_Y)
        mat.ls3d_env_ydet = bool(raw_flags & MTL_ENV_DETERMINED_Y)
        mat.ls3d_env_zdet = bool(raw_flags & MTL_ENV_DETERMINED_Z)
        mat.ls3d_alpha_effect = bool(raw_flags & MTL_ENV_ADDEFFECT)

        # Misc
        mat.ls3d_misc_unlit = bool(raw_flags & MTL_MISC_UNLIT)
        # Z-Write is often associated with Additive in tools, but we keep it separate
        mat.ls3d_misc_zwrite = bool(raw_flags & MTL_ADDITIVE) 

        # 4. READ TEXTURE NAMES
        env_opacity = 0.0
        env_tex_name = ""
        diff_tex_name = ""
        alpha_tex_name = ""
        
        if mat.ls3d_env_enabled:
            env_opacity = struct.unpack("<f", f.read(4))[0]
            env_tex_name = self.read_string(f)
            
        diff_tex_name = self.read_string(f)
        if diff_tex_name: mat.name = diff_tex_name
        
        if mat.ls3d_alpha_enabled:
            alpha_tex_name = self.read_string(f)
            
        if mat.ls3d_diff_anim:
            mat.ls3d_diff_frame_count = struct.unpack("<I", f.read(4))[0]
            f.read(2) 
            mat.ls3d_diff_frame_period = struct.unpack("<I", f.read(4))[0]
            f.read(8)

        # 5. RECONSTRUCT NODE GRAPH
        ls3d_group = get_or_create_ls3d_group()
        group_node = tree.nodes.new('ShaderNodeGroup')
        group_node.node_tree = ls3d_group
        group_node.location = (0, 0)
        group_node.width = 300
        
        if "Opacity" in group_node.inputs:
            group_node.inputs["Opacity"].default_value = opacity * 100.0

        output = tree.nodes.new('ShaderNodeOutputMaterial')
        output.location = (350, 0)
        tree.links.new(group_node.outputs["BSDF"], output.inputs["Surface"])

        if diff_tex_name:
            tex = tree.nodes.new('ShaderNodeTexImage')
            tex.image = self.get_or_load_texture(diff_tex_name)
            tex.location = (-400, 200)
            tex.label = "Diffuse Map"
            if mat.ls3d_alpha_colorkey: tex.interpolation = 'Closest'
            
            if "Diffuse Map" in group_node.inputs:
                tree.links.new(tex.outputs["Color"], group_node.inputs["Diffuse Map"])
            if mat.ls3d_alpha_imgalpha and "Alpha Map" in group_node.inputs:
                tree.links.new(tex.outputs["Alpha"], group_node.inputs["Alpha Map"])

        if alpha_tex_name:
            tex = tree.nodes.new('ShaderNodeTexImage')
            tex.image = self.get_or_load_texture(alpha_tex_name)
            tex.location = (-400, -100)
            tex.label = "Alpha Map"
            if "Alpha Map" in group_node.inputs:
                tree.links.new(tex.outputs["Color"], group_node.inputs["Alpha Map"])
            mat.blend_method = 'BLEND'

        if env_tex_name and mat.ls3d_env_enabled:
            frame = tree.nodes.new('NodeFrame'); frame.label = "Reflection"; frame.location = (-600, -400)
            coord = tree.nodes.new('ShaderNodeTexCoord'); coord.location = (-1100, -400); coord.parent = frame
            mapping = tree.nodes.new('ShaderNodeMapping'); mapping.location = (-900, -400); mapping.parent = frame
            env_img = tree.nodes.new('ShaderNodeTexImage'); env_img.location = (-700, -400); env_img.projection = 'SPHERE'; env_img.parent = frame
            env_img.image = self.get_or_load_texture(env_tex_name); env_img.label = "Reflection Map"
            
            env_grp_data = get_or_create_env_group()
            env_group = tree.nodes.new('ShaderNodeGroup'); env_group.node_tree = env_grp_data; env_group.location = (-400, -400); env_group.parent = frame
            
            if "Intensity" in env_group.inputs: env_group.inputs["Intensity"].default_value = env_opacity
            
            tree.links.new(coord.outputs["Reflection"], mapping.inputs["Vector"])
            tree.links.new(mapping.outputs["Vector"], env_img.inputs["Vector"])
            tree.links.new(env_img.outputs["Color"], env_group.inputs["Color"])
            
            if "Reflection" in group_node.inputs:
                tree.links.new(env_group.outputs["Output"], group_node.inputs["Reflection"])

        # 6. BLENDER SETTINGS (Blender 5.0 compatible)
        mat.use_backface_culling = not mat.ls3d_diff_2sided
        if mat.ls3d_alpha_colorkey:
            mat.blend_method = 'CLIP'
            # Fallback for 5.0: If opacity is < 100%, we need BLEND to see it fade
            if group_node.inputs["Opacity"].default_value < 100.0: mat.blend_method = 'BLEND'
        elif mat.ls3d_alpha_addmix or mat.ls3d_alpha_enabled or mat.ls3d_alpha_imgalpha:
            mat.blend_method = 'BLEND'
        else:
            mat.blend_method = 'OPAQUE'
        
        return mat
    
    def deserialize_object(self, f, materials, mesh, mesh_data, culling_flags):
        instance_id = struct.unpack("<H", f.read(2))[0]
        if instance_id > 0:
            return None, None
            
        vertices_per_lod = []
        num_lods = struct.unpack("<B", f.read(1))[0]
        
        base_name = mesh.name
        
        for lod_idx in range(num_lods):
            # 1. READ DISTANCE
            clipping_range = struct.unpack("<f", f.read(4))[0]
            
            # 2. CREATE OBJECT & ASSIGN DISTANCE
            if lod_idx > 0:
                name = f"{base_name}_lod{lod_idx}"
                mesh_data = bpy.data.meshes.new(name)
                new_mesh = bpy.data.objects.new(name, mesh_data)
                new_mesh.parent = mesh 
                new_mesh.matrix_local = Matrix.Identity(4) 
                bpy.context.collection.objects.link(new_mesh)
                
                # Assign to child LOD
                new_mesh.ls3d_lod_dist = clipping_range
                new_mesh.cull_flags = culling_flags
                new_mesh.hide_set(True)
                new_mesh.hide_render = True
                
                current_mesh = mesh_data
            else:
                # Assign to Root LOD
                mesh.ls3d_lod_dist = clipping_range
                current_mesh = mesh_data

            num_vertices = struct.unpack("<H", f.read(2))[0]
            vertices_per_lod.append(num_vertices)
            
            # --- GEOMETRY ---
            raw_pos = []
            raw_norm = []
            raw_uv = []
            
            for _ in range(num_vertices):
                data = struct.unpack("<3f3f2f", f.read(32))
                raw_pos.append((data[0], data[2], data[1]))
                raw_norm.append((data[3], data[5], data[4]))
                raw_uv.append((data[6], 1.0 - data[7]))

            bm = bmesh.new()
            bm_verts = [bm.verts.new(p) for p in raw_pos]
            bm.verts.ensure_lookup_table()
            
            num_face_groups = struct.unpack("<B", f.read(1))[0]
            
            for group_idx in range(num_face_groups):
                num_faces = struct.unpack("<H", f.read(2))[0]
                raw_faces = struct.unpack(f"<{num_faces*3}H", f.read(num_faces * 6))
                mat_idx = struct.unpack("<H", f.read(2))[0]
                
                slot_index = 0
                if mat_idx > 0 and (mat_idx - 1) < len(materials):
                    target_mat = materials[mat_idx - 1]
                    if target_mat.name in current_mesh.materials:
                        slot_index = current_mesh.materials.find(target_mat.name)
                    else:
                        current_mesh.materials.append(target_mat)
                        slot_index = len(current_mesh.materials) - 1
                
                for i in range(0, len(raw_faces), 3):
                    try:
                        v1, v2, v3 = bm_verts[raw_faces[i]], bm_verts[raw_faces[i+2]], bm_verts[raw_faces[i+1]]
                        face = bm.faces.new((v1, v2, v3))
                        face.material_index = slot_index
                        face.smooth = True 
                    except ValueError: pass

            bm.to_mesh(current_mesh)
            bm.free()
            
            # --- NORMALS & UVS ---
            if num_vertices > 0:
                uv_layer = current_mesh.uv_layers.new(name="UVMap")
                loop_normals = []
                for loop in current_mesh.loops:
                    v_idx = loop.vertex_index
                    uv_layer.data[loop.index].uv = raw_uv[v_idx]
                    loop_normals.append(raw_norm[v_idx])
                
                try: current_mesh.normals_split_custom_set(loop_normals)
                except: pass

                if hasattr(current_mesh, "use_auto_smooth"):
                    current_mesh.use_auto_smooth = True
                current_mesh.validate(clean_customdata=False)
            
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
        frame_type = struct.unpack("<B", f.read(1))[0]
        visual_type = 0
        visual_flags = (128, 42) 
        
        if frame_type == FRAME_VISUAL:
            visual_type = struct.unpack("<B", f.read(1))[0]
            visual_flags = struct.unpack("<2B", f.read(2))
            
        parent_id = struct.unpack("<H", f.read(2))[0]
        position = struct.unpack("<3f", f.read(12))
        scale = struct.unpack("<3f", f.read(12))
        rot = struct.unpack("<4f", f.read(16)) 
        
        pos = (position[0], position[2], position[1])
        scl = (scale[0], scale[2], scale[1])
        rot_tuple = (rot[0], rot[1], rot[3], rot[2])
        
        scale_mat = Matrix.Diagonal(scl).to_4x4()
        rot_mat = Quaternion(rot_tuple).to_matrix().to_4x4()
        trans_mat = Matrix.Translation(pos)
        transform_mat = trans_mat @ rot_mat @ scale_mat
        
        # Read Flag and convert to int just to be safe
        culling_flags = int(struct.unpack("<B", f.read(1))[0])
        name = self.read_string(f)
        user_props = self.read_string(f)
        
        self.frame_types[self.frame_index] = frame_type
        if parent_id > 0:
            self.parenting_info.append((self.frame_index, parent_id))
        
        mesh = None
        empty = None
        
        if frame_type == FRAME_VISUAL:
            if visual_type in (VISUAL_OBJECT, VISUAL_LITOBJECT):
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = str(visual_type)
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                self.frame_index += 1
                mesh.matrix_local = transform_mat
                
                mesh.cull_flags = culling_flags
                self.deserialize_object(f, materials, mesh, mesh_data, culling_flags)
            
            elif visual_type == VISUAL_BILLBOARD:
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = '4'
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                self.frame_index += 1
                mesh.matrix_local = transform_mat
                
                mesh.cull_flags = culling_flags
                self.deserialize_object(f, materials, mesh, mesh_data, culling_flags)
                self.deserialize_billboard(f, mesh)

            elif visual_type == VISUAL_MIRROR:
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = '8'
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                self.frame_index += 1
                mesh.matrix_local = transform_mat
                self.deserialize_mirror(f, mesh)

            elif visual_type in (VISUAL_SINGLEMESH, VISUAL_SINGLEMORPH, VISUAL_MORPH):
                mesh_data = bpy.data.meshes.new(name + "_mesh")
                mesh = bpy.data.objects.new(name, mesh_data)
                bpy.context.collection.objects.link(mesh)
                mesh.visual_type = str(visual_type)
                frames.append(mesh)
                self.frames_map[self.frame_index] = mesh
                mesh.matrix_local = transform_mat
                
                mesh.cull_flags = culling_flags
                num_lods, verts_per_lod = self.deserialize_object(f, materials, mesh, mesh_data, culling_flags)
                
                if visual_type != VISUAL_MORPH:
                    self.deserialize_singlemesh(f, num_lods, mesh)
                    self.bones_map[self.frame_index] = self.base_bone_name
                
                if visual_type != VISUAL_SINGLEMESH:
                    self.deserialize_morph(f, mesh, verts_per_lod)
                
                self.frame_index += 1
            
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
                    mesh.cull_flags = culling_flags
                    self.deserialize_object(f, materials, mesh, mesh_data, culling_flags)
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
            _ = f.read(64) 
            bone_id = struct.unpack("<I", f.read(4))[0]
            if self.armature:
                self.joints.append((name, transform_mat, parent_id, bone_id))
                self.bone_nodes[bone_id] = name
                self.bones_map[self.frame_index] = name
                self.frames_map[self.frame_index] = name
                self.frame_index += 1
        
        target_obj = mesh if mesh else empty
        if target_obj:
            target_obj.cull_flags = culling_flags
            target_obj.ls3d_user_props = user_props
            target_obj["Frame Properties"] = user_props 
            
            if frame_type == FRAME_VISUAL:
                target_obj.render_flags = visual_flags[0]
                target_obj.render_flags2 = visual_flags[1]
                
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

# --- PROPERTY HELPER FUNCTIONS ---
# These must exist before register() is called

def get_flag_bit(self, prop_name, bit_index):
    """Returns True if the specific bit is set in the integer property."""
    value = getattr(self, prop_name, 0)
    return (value & (1 << bit_index)) != 0

def set_flag_bit(self, value, prop_name, bit_index):
    """Sets or clears a specific bit in the integer property."""
    current = getattr(self, prop_name, 0)
    if value:
        setattr(self, prop_name, current | (1 << bit_index))
    else:
        setattr(self, prop_name, current & ~(1 << bit_index))

def make_getter(prop_name, bit_index):
    return lambda self: get_flag_bit(self, prop_name, bit_index)

def make_setter(prop_name, bit_index):
    return lambda self, value: set_flag_bit(self, value, prop_name, bit_index)

# --- REGISTRATION ---

def unregister():
    # 1. Clean up Menu Entries
    try:
        bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    except: pass

    # 2. Clean up Properties
    # (Delete all the ls3d_... properties here)
    del bpy.types.Material.ls3d_diffuse_color
    del bpy.types.Material.ls3d_ambient_color
    del bpy.types.Material.ls3d_emission_color
    del bpy.types.Material.ls3d_diff_enabled
    del bpy.types.Material.ls3d_diff_colored
    del bpy.types.Material.ls3d_diff_anim
    del bpy.types.Material.ls3d_diff_frame_count
    del bpy.types.Material.ls3d_diff_frame_period
    del bpy.types.Material.ls3d_diff_mipmap
    del bpy.types.Material.ls3d_diff_2sided
    del bpy.types.Material.ls3d_env_enabled
    del bpy.types.Material.ls3d_env_overlay
    del bpy.types.Material.ls3d_env_multiply
    del bpy.types.Material.ls3d_env_additive
    del bpy.types.Material.ls3d_env_yproj
    del bpy.types.Material.ls3d_env_ydet
    del bpy.types.Material.ls3d_env_zdet
    del bpy.types.Material.ls3d_alpha_enabled
    del bpy.types.Material.ls3d_alpha_effect
    del bpy.types.Material.ls3d_alpha_colorkey
    del bpy.types.Material.ls3d_alpha_addmix
    del bpy.types.Material.ls3d_alpha_anim
    del bpy.types.Material.ls3d_alpha_imgalpha
    del bpy.types.Material.ls3d_disable_tex
    
    # Delete new ones
    del bpy.types.Material.ls3d_calc_reflect_y
    del bpy.types.Material.ls3d_proj_reflect_y
    del bpy.types.Material.ls3d_proj_reflect_z
    
    del bpy.types.Material.ls3d_misc_unlit
    del bpy.types.Material.ls3d_misc_tile_u
    del bpy.types.Material.ls3d_misc_tile_v
    del bpy.types.Material.ls3d_misc_zwrite

    # ... Delete Object properties (cull_flags, etc) ... 
    del bpy.types.Object.visual_type
    del bpy.types.Object.cull_flags
    del bpy.types.Object.render_flags
    del bpy.types.Object.render_flags2
    del bpy.types.Object.rf1_cast_shadow
    del bpy.types.Object.rf1_receive_shadow
    del bpy.types.Object.rf1_draw_last
    del bpy.types.Object.rf1_zbias
    del bpy.types.Object.rf1_active
    del bpy.types.Object.rf2_decal
    del bpy.types.Object.rf2_stencil
    del bpy.types.Object.rf2_mirror
    del bpy.types.Object.rf2_proj
    del bpy.types.Object.rf2_nofog
    del bpy.types.Object.cf_visible
    del bpy.types.Object.cf_coll_player
    del bpy.types.Object.cf_coll_ai
    del bpy.types.Object.cf_coll_vehicle
    del bpy.types.Object.cf_coll_camera
    del bpy.types.Object.cf_coll_proj
    del bpy.types.Object.cf_coll_item
    del bpy.types.Object.cf_light_int
    del bpy.types.Object.ls3d_user_props
    del bpy.types.Object.ls3d_lod_dist
    del bpy.types.Object.ls3d_portal_flags
    del bpy.types.Object.ls3d_portal_near
    del bpy.types.Object.ls3d_portal_far
    del bpy.types.Object.ls3d_portal_unknown
    del bpy.types.Object.ls3d_portal_enabled
    del bpy.types.Object.ls3d_sector_flags1
    del bpy.types.Object.ls3d_sector_flags2
    del bpy.types.Object.rot_axis
    del bpy.types.Object.rot_mode
    del bpy.types.Object.mirror_color
    del bpy.types.Object.mirror_dist
    del bpy.types.Object.bbox_min
    del bpy.types.Object.bbox_max

    # 3. Unregister Classes
    bpy.utils.unregister_class(LS3D_OT_AddEnvSetup)
    bpy.utils.unregister_class(LS3D_OT_AddNode)
    bpy.utils.unregister_class(The4DSPanelMaterial)
    bpy.utils.unregister_class(The4DSPanel)
    bpy.utils.unregister_class(Import4DS)
    bpy.utils.unregister_class(Export4DS)


def register():
    # --- HELPER / ENUMS ---
    bpy.types.Object.visual_type = EnumProperty(
        name="Mesh Type",
        items=(
            ('0', "Object", "Standard static mesh"), 
            ('1', "Lit Object", "Static object with pre-calc lighting"), 
            ('2', "Single Mesh", "Optimized single-buffer mesh"), 
            ('3', "Single Morph", "Single mesh with morphs"), 
            ('4', "Billboard", "Sprite rotating to camera"), 
            ('5', "Morph", "Standard mesh with morphs"), 
            ('6', "Lens", "Lens flare"), 
            ('7', "Projector", "Texture projector"), 
            ('8', "Mirror", "Reflection surface"), 
            ('9', "Emitor", "Particle emitter"), 
            ('10', "Shadow", "Shadow volume mesh"), 
            ('11', "Land Patch", "Terrain geometry")
        ),
        default='0'
    )
    
    # --- RAW INTEGER STORAGE ---
    bpy.types.Object.cull_flags = IntProperty(name="Culling & Collision Flags", default=1, min=0, max=255, description="Collision and Visibility bitmask") # Cull Flags
    bpy.types.Object.render_flags = IntProperty(name="Render Flags Primary", default=128, min=0, max=255, description="Visual rendering properties") # Render Flags 1
    bpy.types.Object.render_flags2 = IntProperty(name="Render Flags Secondary", default=8, min=0, max=255, description="Logical rendering properties") # Render Flags 2
    
    # --- RENDER FLAGS 1 (Visual) ---
    bpy.types.Object.rf1_cast_shadow = BoolProperty(name="Casts Shadow", get=make_getter("render_flags", 0), set=make_setter("render_flags", 0), description="Object casts a shadow")
    bpy.types.Object.rf1_receive_shadow = BoolProperty(name="Receives Shadow", get=make_getter("render_flags", 1), set=make_setter("render_flags", 1), description="Object receives shadows")
    bpy.types.Object.rf1_draw_last = BoolProperty(name="Draw Last (Alpha)", get=make_getter("render_flags", 2), set=make_setter("render_flags", 2), description="Forces the object to render after opaque objects. Required for transparent objects")
    bpy.types.Object.rf1_zbias = BoolProperty(name="Z-Bias (Overlay)", get=make_getter("render_flags", 3), set=make_setter("render_flags", 3), description="Disables Z-Buffer depth check (Always on top, prevents Z-Fighting of two coplanar surfaces)")
    bpy.types.Object.rf1_active = BoolProperty(name="Active", get=make_getter("render_flags", 7), set=make_setter("render_flags", 7), description="Renderer sees and renders the object normally")

    # --- RENDER FLAGS 2 (Logic) ---
    bpy.types.Object.rf2_decal = BoolProperty(name="Is Decal", get=make_getter("render_flags2", 0), set=make_setter("render_flags2", 0), description="Draws coplanar on top of other mesh")
    bpy.types.Object.rf2_stencil = BoolProperty(name="Shadow Volume", get=make_getter("render_flags2", 1), set=make_setter("render_flags2", 1), description="Object is a stencil shadow object/volume")
    bpy.types.Object.rf2_mirror = BoolProperty(name="Mirrorable", get=make_getter("render_flags2", 2), set=make_setter("render_flags2", 2), description="Visible in mirrors")
    bpy.types.Object.rf2_proj = BoolProperty(name="Recieves Projection", get=make_getter("render_flags2", 5), set=make_setter("render_flags2", 5), description="Receives projected textures (headlights)")
    bpy.types.Object.rf2_nofog = BoolProperty(name="No Fog", get=make_getter("render_flags2", 7), set=make_setter("render_flags2", 7), description="Disables fog shading for this object")

    # --- CULL FLAGS (Collision/Visibility) ---
    bpy.types.Object.cf_visible = BoolProperty(name="Visible", get=make_getter("cull_flags", 0), set=make_setter("cull_flags", 0), description="Global object culling (Can be toggled with scripts)")
    bpy.types.Object.cf_coll_player = BoolProperty(name="Player", get=make_getter("cull_flags", 1), set=make_setter("cull_flags", 1), description="Collision with Player/Humans")
    bpy.types.Object.cf_coll_ai = BoolProperty(name="AI/Bullet", get=make_getter("cull_flags", 2), set=make_setter("cull_flags", 2), description="Collision with AI and Bullets (Small)")
    bpy.types.Object.cf_coll_vehicle = BoolProperty(name="Vehicle", get=make_getter("cull_flags", 3), set=make_setter("cull_flags", 3), description="Collision with Vehicles")
    bpy.types.Object.cf_coll_camera = BoolProperty(name="Camera", get=make_getter("cull_flags", 4), set=make_setter("cull_flags", 4), description="Collision with Camera")
    bpy.types.Object.cf_coll_proj = BoolProperty(name="Projectile", get=make_getter("cull_flags", 5), set=make_setter("cull_flags", 5), description="Collision with Rockets/Grenades")
    bpy.types.Object.cf_coll_item = BoolProperty(name="Item/Move", get=make_getter("cull_flags", 6), set=make_setter("cull_flags", 6), description="Collision with Movable items")
    bpy.types.Object.cf_light_int = BoolProperty(name="Light Interact", get=make_getter("cull_flags", 7), set=make_setter("cull_flags", 7), description="Interacts with scene lighting")

    # --- OTHER PARAMS ---
    bpy.types.Object.ls3d_user_props = StringProperty(name="String Parameters", description="Frame properties")
    bpy.types.Object.ls3d_lod_dist = FloatProperty(name="Fade-in Distance", default=100.0, description="Distance at which this LOD becomes visible")
    
    # Portal/Sector
    bpy.types.Object.ls3d_portal_flags = IntProperty(name="Flags", default=4)
    bpy.types.Object.ls3d_portal_near = FloatProperty(name="Near Range", default=0.0)
    bpy.types.Object.ls3d_portal_far = FloatProperty(name="Far Range", default=100.0)
    bpy.types.Object.ls3d_portal_unknown = FloatProperty(name="Unknown", default=0.0)
    bpy.types.Object.ls3d_portal_enabled = BoolProperty(name="Enabled", get=make_getter("ls3d_portal_flags", 2), set=make_setter("ls3d_portal_flags", 2))
    
    bpy.types.Object.ls3d_sector_flags1 = IntProperty(default=2049, name="Sector Flags 1")
    bpy.types.Object.ls3d_sector_flags2 = IntProperty(default=0, name="Sector Flags 2")
    
    # Specifics
    bpy.types.Object.rot_axis = EnumProperty(name="Rotation Axis", items=(('0', "X", ""), ('1', "Z", ""), ('2', "Y", "")), default='1')
    bpy.types.Object.rot_mode = EnumProperty(name="Rotation Mode", items=(('0', "All Axes", ""), ('1', "Single Axis", "")), default='0')
    bpy.types.Object.mirror_color = FloatVectorProperty(subtype='COLOR', default=(0,0,0), name="Mirror Color", description="Tint color of the Mirror")
    bpy.types.Object.mirror_dist = FloatProperty(default=100.0, name="Mirror Distance", description="Distance of how far the Mirror will mirror objects")
    bpy.types.Object.bbox_min = FloatVectorProperty(subtype='XYZ')
    bpy.types.Object.bbox_max = FloatVectorProperty(subtype='XYZ')

    # --- MATERIAL PROPS ---
    
    # 1. Colors
    bpy.types.Material.ls3d_diffuse_color = FloatVectorProperty(subtype='COLOR', default=(1,1,1), name="Diffuse Color", description="Main surface color")
    bpy.types.Material.ls3d_ambient_color = FloatVectorProperty(subtype='COLOR', default=(0.5,0.5,0.5), name="Ambient Color", description="Environment/Shadow color influence")
    bpy.types.Material.ls3d_emission_color = FloatVectorProperty(subtype='COLOR', default=(0,0,0), name="Emission Color", description="Self-illumination color")
    
    # 2. Diffuse Flags
    bpy.types.Material.ls3d_diff_enabled = BoolProperty(default=True, name="Diffuse Enabled", description="Enable diffuse texturing (MTL_DIFFUSETEX)")
    bpy.types.Material.ls3d_diff_colored = BoolProperty(name="Use Vertex Colors", description="Blend vertex colors with texture (MTL_COLORED)")
    bpy.types.Material.ls3d_diff_anim = BoolProperty(name="Animated Texture", description="Enable texture animation (MTL_ANIMATED_DIFFUSE)")
    bpy.types.Material.ls3d_diff_frame_count = IntProperty(default=0, name="Frame Count")
    bpy.types.Material.ls3d_diff_frame_period = IntProperty(default=0, name="Frame Period (ms)")
    bpy.types.Material.ls3d_diff_mipmap = BoolProperty(default=True, name="Use MipMaps", description="Enable mipmapping (MTL_MIPMAP)")
    bpy.types.Material.ls3d_diff_2sided = BoolProperty(name="Double Sided", description="Render both sides of faces (MTL_DOUBLESIDED)")
    
    # 3. Environment Flags
    bpy.types.Material.ls3d_env_enabled = BoolProperty(name="Environment Map", description="Enable environmental reflection (MTL_ENVMAP)")
    bpy.types.Material.ls3d_env_overlay = BoolProperty(name="Env Overlay", description="Overlay environment on diffuse (MTL_ENV_OVERLAY)")
    bpy.types.Material.ls3d_env_multiply = BoolProperty(default=True, name="Env Multiply", description="Multiply environment with diffuse (MTL_ENV_MULTIPLY)")
    bpy.types.Material.ls3d_env_additive = BoolProperty(name="Env Additive", description="Add environment to diffuse (MTL_ENV_ADDITIVE)")
    bpy.types.Material.ls3d_env_yproj = BoolProperty(name="Env Y-Proj", description="Y-Axis Projection (MTL_ENV_PROJECT_Y)")
    bpy.types.Material.ls3d_env_ydet = BoolProperty(name="Env Y-Det", description="Y-Determined mapping (MTL_ENV_DETERMINED_Y)")
    bpy.types.Material.ls3d_env_zdet = BoolProperty(name="Env Z-Det", description="Z-Determined mapping (MTL_ENV_DETERMINED_Z)")
    
    # 4. Alpha Flags
    bpy.types.Material.ls3d_alpha_enabled = BoolProperty(name="Alpha Map", description="Enable alpha mask texture")
    bpy.types.Material.ls3d_alpha_effect = BoolProperty(name="Alpha Effect", description="Special alpha effect mode (MTL_ENV_ADDEFFECT)")
    bpy.types.Material.ls3d_alpha_colorkey = BoolProperty(name="Color Key", description="Hard cutout transparency. Color key is the first indexed value in BMP color table")
    bpy.types.Material.ls3d_alpha_addmix = BoolProperty(name="Additive Mix", description="Additive blending (MTL_ADDITIVE)")
    bpy.types.Material.ls3d_alpha_anim = BoolProperty(name="Animated Alpha", description="Animated alpha texture (MTL_ANIMATED_ALPHA)")
    bpy.types.Material.ls3d_alpha_imgalpha = BoolProperty(name="Use Image Alpha", description="Use alpha channel embedded in the diffuse texture (MTL_ALPHA_IN_TEX)")
    
    # 5. Misc & Reflection Calc
    bpy.types.Material.ls3d_disable_tex = BoolProperty(name="Disable Texture", description="Force disable texturing (MTL_ENV_DISABLE_TEX)")
    
    bpy.types.Material.ls3d_calc_reflect_y = BoolProperty(name="Calc Reflect Y (Wet)", description="Calculate Reflection Y. Used for Wet Roads (MTL_CALCREFLECTTEXY)")
    bpy.types.Material.ls3d_proj_reflect_y = BoolProperty(name="Proj Reflect Y", description="Project Reflection Y (MTL_PROJECTREFLECTTEXY)")
    bpy.types.Material.ls3d_proj_reflect_z = BoolProperty(name="Proj Reflect Z", description="Project Reflection Z (MTL_PROJECTREFLECTTEXZ)")
    
    bpy.types.Material.ls3d_misc_unlit = BoolProperty(name="Unlit", description="Disable lighting (FullBright) (MTL_MISC_UNLIT)")
    bpy.types.Material.ls3d_misc_tile_u = BoolProperty(default=True, name="Tile U", description="Repeat texture horizontally")
    bpy.types.Material.ls3d_misc_tile_v = BoolProperty(default=True, name="Tile V", description="Repeat texture vertically")
    bpy.types.Material.ls3d_misc_zwrite = BoolProperty(name="Z-Write", description="Write to Z-Buffer")

    # Classes
    bpy.utils.register_class(LS3D_OT_AddEnvSetup)
    bpy.utils.register_class(LS3D_OT_AddNode)
    bpy.utils.register_class(The4DSPanelMaterial)
    bpy.utils.register_class(The4DSPanel)
    bpy.utils.register_class(Import4DS)
    bpy.utils.register_class(Export4DS)
    
    try:
        bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
        bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    except: pass
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    
if __name__ == "__main__":
    register()
