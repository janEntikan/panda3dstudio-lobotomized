from .basis import *


class ImportManager:

    def __init__(self):

        self._model_root = None
        self._hierarchy = {"quadrangulate": False}
        self._obj_index = 0
        self._geom_obj_indices = []
        self._coll_obj_indices = []
        self._obj_names = []
        self._imported_file = ""
        self._imported_file_type = ""
        self._imported_materials = []
        self._imported_objs = []

        Mgr.add_app_updater("import", self.__update_import)

    def __prepare_import(self, filename):

        self._imported_file = filename
        path = Filename.from_os_specific(filename)
        model_root = Mgr.load_model(path, noCache=True, okMissing=True)

        if not model_root:
            return

        if not model_root.node().is_of_type(ModelRoot):
            child = model_root
            model_root = NodePath(ModelRoot(""))
            child.reparent_to(model_root)

        if not model_root.children:
            return

        self._imported_file_type = path.get_extension()
        self._model_root = model_root
        hierarchy = self._hierarchy

        obj_names = GD["obj_names"]
        self._obj_names = new_obj_names = []
        geom_indices = self._geom_obj_indices
        coll_indices = self._coll_obj_indices
        node_paths = [(model_root, 0, None)]

        while node_paths:

            node_path, index, parent_index = node_paths.pop()

            if node_path.is_empty():
                continue

            child_indices = []
            node_data = {"node_path": node_path, "child_indices": child_indices}
            hierarchy[index] = node_data
            children = node_path.children

            for child in children:
                self._obj_index += 1
                child_index = self._obj_index
                child_indices.append(child_index)
                node_paths.append((child, child_index, index))

            if node_path is model_root:
                continue

            old_name = node_path.name
            new_name = obj_name = old_name.strip()

            if not new_name:
                new_name = "object 0001"

            new_name = get_unique_name(new_name, obj_names + new_obj_names)

            if not old_name:
                old_name = "<Unnamed>"

            node = node_path.node()
            node_type = node.type.name
            node_data["parent_index"] = parent_index
            node_data["old_name"] = old_name
            node_data["new_name"] = new_name

            if node_type == "GeomNode" and Geom.PT_polygons in [geom.primitive_type
                    for geom in node.get_geoms()]:
                node_data["geom_type"] = "regular"
                geom_indices.append(index)
            elif node_type == "CollisionNode":
                new_name = obj_name if obj_name else "collision object 0001"
                new_name = get_unique_name(new_name, obj_names + new_obj_names)
                node_data["new_name"] = new_name
                node_data["geom_type"] = "collision"
                coll_indices.append(index)
            else:
                node_data["geom_type"] = "none"

            new_obj_names.append(new_name)

        Mgr.update_remotely("import", hierarchy, new_obj_names)

    def __cancel_import(self):

        self._model_root.detach_node()
        self._model_root = None
        self._hierarchy = {"quadrangulate": False}
        self._obj_index = 0
        self._geom_obj_indices = []
        self._coll_obj_indices = []
        self._obj_names = []
        self._imported_file = ""
        self._imported_file_type = ""
        self._imported_materials = []

    def __create_point_helper(self, name, transform):

        size = 10.
        on_top = True
        colors = {"unselected": (.5, 0., 1., 1.), "selected": (1., 1., 1., 1.)}
        point_helper = Mgr.do("create_custom_point_helper", name, size, on_top, colors, transform)
        point_helper.update_pos()

        return point_helper

    def __create_collision_planes(self, plane_data, obj_names):

        # check if the given planes form an inverted box
        if len(plane_data) == 6:

            data_to_process = plane_data[:]
            opposite_sides = []
            side_normals = []

            while data_to_process:

                side_plane = data_to_process.pop()
                point = side_plane.get_point()
                normal = V3D(side_plane.get_normal())

                # check if side is perpendicular to previous sides
                for other_normal in side_normals:
                    if abs(normal * other_normal) > .001:
                        break

                # check if there is a side facing this one
                for other_side_plane in data_to_process:

                    other_normal = V3D(other_side_plane.get_normal())

                    # check if planes are facing opposite directions
                    if normal * other_normal < -.99:

                        dist = other_side_plane.dist_to_plane(point)

                        # check if planes are facing each other
                        # ("inner" half-spaces do not intersect)
                        if dist > 0.:
                            opposite_sides.append((side_plane, other_side_plane, dist))
                            side_normals.append(normal)
                            data_to_process.remove(other_side_plane)
                            break

                else:

                    break

            if len(side_normals) == 3:

                up_vec = V3D(Vec3.up())
                dot_prod = 0.
                z_vec = None
                xy_plane_data = None

                # use the normal closest to the world Z vector as the local Z vector
                for normal, side_data in zip(side_normals, opposite_sides):

                    dot_prod_tmp = up_vec * normal

                    if abs(dot_prod_tmp) > abs(dot_prod):
                        dot_prod = dot_prod_tmp
                        z_vec = normal
                        xy_plane_data = side_data

                side_normals.remove(z_vec)
                opposite_sides.remove(xy_plane_data)

                if dot_prod < 0.:
                    z_vec *= -1.
                    xy_plane = xy_plane_data[1]
                else:
                    xy_plane = xy_plane_data[0]

                x_vec = side_normals[0]
                y_vec = z_vec ** x_vec
                yz_plane_data, xz_plane_data = opposite_sides
                yz_plane = yz_plane_data[0]

                x = yz_plane_data[2]
                y = xz_plane_data[2]
                z = xy_plane_data[2]

                point = Point3()
                xy_plane.intersects_plane(point, Vec3(), yz_plane)
                corners = [xz_plane.project(point) for xz_plane in xz_plane_data[:2]]
                pos = sum(corners, Point3()) * .5 + x_vec * .5 * x

                quat = Quat()
                look_at(quat, y_vec, z_vec)
                hpr = quat.get_hpr()

                name = "object 0001"
                name = get_unique_name(name, obj_names)
                obj_names.append(name)

                segments = {"x": 1, "y": 1, "z": 1}
                creator = Mgr.do("create_custom_box", name, x, y, z, segments, pos, inverted=True)
                model = next(creator)
                model.register(restore=False)
                model.pivot.set_hpr(hpr)

                return [model]

        plane_models = []

        for plane in plane_data:

            pos = plane.project(Point3(0., 0., 0.))
            normal = plane.get_normal()

            if normal.x < -.999:
                hpr = VBase3(0., 0., 90.)
            elif normal.x > .999:
                hpr = VBase3(0., 0., -90.)
            elif normal.y < -.999:
                hpr = VBase3(0., -90., 0.)
            elif normal.y > .999:
                hpr = VBase3(0., 90., 0.)
            elif normal.z < -.999:
                hpr = VBase3(0., 180., 0.)
            elif normal.z > .999:
                hpr = VBase3(0., 0., 0.)
            else:
                point = Point3(normal)
                # project the normal onto the world XY-plane...
                point.z = 0.
                # ...and project that projected point onto the given plane
                # to compute its local forward vector
                y_vec = plane.project(point) - pos
                quat = Quat()
                look_at(quat, y_vec, normal)
                hpr = quat.get_hpr()

            name = "object 0001"
            name = get_unique_name(name, obj_names)
            obj_names.append(name)

            x = y = 10.
            segments = {"x": 1, "y": 1}
            creator = Mgr.do("create_custom_plane", name, x, y, segments, pos)
            model = next(creator)
            model.register(restore=False)
            model.pivot.set_hpr(hpr)
            plane_models.append(model)

        return plane_models

    def __create_collision_primitive(self, obj_type, *args):

        if obj_type in ("CollisionSphere", "CollisionInvSphere"):
            name, radius, pos = args
            segments = 16
            inverted = obj_type == "CollisionInvSphere"
            model = Mgr.do("create_custom_sphere", name, radius, segments, pos, inverted)
        elif obj_type == "CollisionCapsule":
            name, radius, height, pos, hpr = args
            segments = {"circular": 12, "height": 1, "caps": 1}
            model = Mgr.do("create_custom_cylinder", name, radius, height, segments, pos)
        elif obj_type == "CollisionBox":
            name, x, y, z, pos = args
            segments = {"x": 1, "y": 1, "z": 1}
            model = Mgr.do("create_custom_box", name, x, y, z, segments, pos)

        model.register(restore=False)

        if obj_type == "CollisionCapsule":
            pivot = model.pivot
            pivot.set_hpr(hpr)
            pivot.set_p(pivot, -90.)

        return model

    def __create_collision_model(self, name, polys, gradual=False):

        coords = []
        poly_count = 0

        vertex_format = GeomVertexFormat.get_v3n3()
        vertex_data = GeomVertexData("locked_geom", vertex_format, Geom.UH_static)
        pos_writer = GeomVertexWriter(vertex_data, "vertex")
        normal_writer = GeomVertexWriter(vertex_data, "normal")
        tris = GeomTriangles(Geom.UH_static)
        tris.set_index_type(Geom.NT_uint32)
        row = 0

        for poly in polys:

            points = [point for point in poly]
            rows_by_pos = {}

            for i, point in enumerate(points):
                for impr_crd in coords:
                    if point == impr_crd:
                        points[i] = impr_crd
                        break
                else:
                    coords.append(point)

            plane = Plane(*poly[:3])
            normal = plane.get_normal()
            pos = points.pop(0)
            pos_writer.add_data3(*pos)
            normal_writer.add_data3(normal)
            rows_by_pos[pos] = row1 = row
            row += 1

            for positions in (points[i:i+2] for i in range(len(points) - 1)):

                tris.add_vertex(row1)

                for pos in positions:
                    if pos in rows_by_pos:
                        tris.add_vertex(rows_by_pos[pos])
                    else:
                        pos_writer.add_data3(*pos)
                        normal_writer.add_data3(normal)
                        rows_by_pos[pos] = row
                        tris.add_vertex(row)
                        row += 1

            if gradual:

                poly_count += 1

                if poly_count == 20:
                    yield
                    poly_count = 0

        geom = Geom(vertex_data)
        geom.add_primitive(tris)
        node = GeomNode("locked_geom")
        node.add_geom(geom)
        node_path = NodePath(node)

        for geom_data in self.__define_locked_geom_data(geom, False, gradual):
            if gradual:
                yield

        model = Mgr.do("create_locked_geom", node_path, geom_data, name=name).model
        model.bbox.update(node_path.get_tight_bounds())
        r, g, b = [random.random() * .4 + .5 for i in range(3)]
        color = (r, g, b, 1.)
        model.set_color(color, update_app=False)
        model.register(restore=False)

        yield model

    def __create_model_group(self, name, transform):

        model_group = Mgr.do("create_group", name, ["model"], "model", transform)

        return model_group

    def __create_collision_group(self, name, transform):

        coll_group = Mgr.do("create_group", name, ["collision"], "collision", transform)

        return coll_group

    def __define_locked_geom_data(self, geom, quadrangulate=False, gradual=False):

        geom_data = []
        coords = []

        src_vert_data = geom.get_vertex_data()
        src_format = src_vert_data.format
        dest_format = Mgr.get("vertex_format_full")
        dest_vert_data = src_vert_data.convert_to(dest_format)
        pos_view = memoryview(dest_vert_data.get_array(0)).cast("B").cast("f")
        col_view = memoryview(dest_vert_data.get_array(1)).cast("B")
        normal_view = memoryview(dest_vert_data.get_array(2)).cast("B").cast("f")

        processed_data = {}
        tris_by_edge = {}
        # keep track of which triangles share edges, so they can be combined into quads
        # afterwards
        adjacent_tris = {}
        indices = geom.get_primitive(0).get_vertex_list()

        def get_quad_vert_index_list(quad):

            tri1, tri2 = quad
            index_list = list(tri1)
            vi1, vi2, vi3 = tri2
            other_indices = (vi1, vi2, vi3, vi1)
            new_index = set(tri2).difference(tri1).pop()
            i = other_indices.index(new_index) + 1
            index_list.insert(index_list.index(other_indices[i]), new_index)

            return index_list

        def get_quad_score(quad):

            vi1, vi2, vi3, vi4 = index_list = get_quad_vert_index_list(quad)
            points = [Point3(*pos_view[vi*3:vi*3+3]) for vi in index_list]
            points.append(points[0])
            vecs = [points[i + 1] - points[i] for i in range(4)]
            lengths = [vec.length_squared() for vec in vecs]

            plane = Plane(*points[:3])
            d = abs(plane.dist_to_plane(points[3]))

            if d < .00001:
                score = 10.
            else:
                q = d * d / max(.00001, max(lengths))
                score = 10. - (1./q if q > 1. else q) * 10.

            for i, j in ((0, 1), (0, 2), (1, 3)):
                q = max(.00001, lengths[i]) / max(.00001, lengths[j])
                score += min(q, 1./q)

            for vec in vecs:
                vec.normalize()

            vecs.append(vecs[0])

            for i in range(4):
                score += 1. - abs(vecs[i].dot(vecs[i + 1]))
                score += vecs[i].cross(vecs[i + 1]).dot(plane.get_normal())

            return score

        if gradual:
            tri_count = 0

        for tri_vert_ids in (indices[i:i+3] for i in range(0, len(indices), 3)):

            vi1, vi2, vi3 = tri = tuple(tri_vert_ids)

            if {tri, (vi2, vi3, vi1), (vi3, vi1, vi2)}.intersection(adjacent_tris):
                continue

            adjacent_tris[tri] = tris = []

            if quadrangulate:

                edge_vert_ids = ((vi1, vi2), (vi2, vi3), (vi3, vi1))

                for vert_ids in edge_vert_ids:

                    if vert_ids[::-1] in tris_by_edge:

                        for other_tri in tris_by_edge[vert_ids[::-1]]:

                            if tris.count(other_tri) == 2:
                                tris.remove(other_tri)
                                tris.remove(other_tri)
                                adjacent_tris[other_tri].remove(tri)
                                adjacent_tris[other_tri].remove(tri)
                            else:
                                tris.append(other_tri)
                                adjacent_tris.setdefault(other_tri, []).append(tri)

                    tris_by_edge.setdefault(vert_ids, []).append(tri)

            if gradual:

                tri_count += 1

                if tri_count == 20:
                    yield
                    tri_count = 0

        if quadrangulate:

            quads = {}
            quad_scores = {}

            for tri, other_tris in adjacent_tris.items():

                quad_list = []

                for other_tri in other_tris:
                    quad = (tri, other_tri)
                    quad_list.append(quad)

                quads[tri] = quad_list

            if gradual:
                quad_count = 0

            for tri, quad_list in quads.items():

                for quad in quad_list:
                    if quad in quad_scores or quad[::-1] in quad_scores:
                        continue
                    quad_scores[quad] = get_quad_score(quad)

                if gradual:

                    quad_count += 1

                    if quad_count == 20:
                        yield
                        quad_count = 0

            sorted_quads = sorted([(v, k) for k, v in quad_scores.items()])
            sorted_quads = [k for _, k in sorted_quads]
            quads = []

            if gradual:
                quad_count = 0

            while sorted_quads:

                quad = sorted_quads.pop()
                quads.append(quad)

                for tri in quad:

                    for other_tri in adjacent_tris.get(tri, []):

                        adjacent_tris[other_tri].remove(tri)
                        other_quad = (tri, other_tri)

                        if other_quad in sorted_quads:
                            sorted_quads.remove(other_quad)
                        elif other_quad[::-1] in sorted_quads:
                            sorted_quads.remove(other_quad[::-1])

                    if tri in adjacent_tris:
                        del adjacent_tris[tri]

                if gradual:

                    quad_count += 1

                    if quad_count == 20:
                        yield
                        quad_count = 0

        else:

            quads = []

        if gradual:
            poly_count = 0

        for poly in quads + [(tri,) for tri in adjacent_tris]:

            if len(poly) == 2:
                index_list = get_quad_vert_index_list(poly)
            else:
                index_list = poly[0]

            for row in index_list:

                vert_data = {}
                pos = Point3(*pos_view[row*3:row*3+3])

                for crd in coords:
                    if pos == crd:
                        pos = crd
                        break
                else:
                    coords.append(pos)

                vert_data["pos"] = pos
                vert_data["color"] = tuple(c / 255. for c in col_view[row*4:row*4+4])
                vert_data["normal"] = Vec3(*normal_view[row*3:row*3+3])
                # instead of filling in the UV data, store the vertex row index for now
                # so the UV coordinates can be set later when creating the LockedGeom
                vert_data["uvs"] = row
                processed_data[row] = vert_data

            poly_verts = [processed_data[i] for i in index_list]
            tris = [[processed_data[i] for i in indices] for indices in poly]
            poly_data = {"verts": poly_verts, "tris": tris}
            geom_data.append(poly_data)

            if gradual:

                poly_count += 1

                if poly_count == 20:
                    yield
                    poly_count = 0

        yield geom_data

    def __import_objects(self, gradual=False):

        model_root = self._model_root
        hierarchy = self._hierarchy
        quadrangulate = hierarchy["quadrangulate"]
        data = [(hierarchy[0], None)]

        while data:

            node_data, parent_id = data.pop()
            node_path = node_data["node_path"]

            if node_path is model_root:

                obj_id = None

            else:

                obj_name = node_data["new_name"]
                node = node_path.node()
                node_type = node.type.name

                if node_type == "GeomNode" and Geom.PT_polygons in [geom.primitive_type
                        for geom in node.get_geoms()]:

                    bounds_node = node_path
                    geom_indices = [i for i, geom in enumerate(node.get_geoms())
                                    if geom.primitive_type == Geom.PT_polygons]
                    geom_count = len(geom_indices)

                    materials = self._imported_materials

                    if geom_count > 1:

                        obj = self.__create_model_group(obj_name, node_path.get_transform())
                        obj_names = GD["obj_names"] + self._obj_names
                        obj_names.remove(obj_name)

                        for i in geom_indices:
                            state = node.get_geom_state(i)
                            tmp_np = node_path.attach_new_node("temp")
                            tmp_np.set_state(state)
                            state = tmp_np.get_net_state()
                            tmp_np.detach_node()
                            new_node = GeomNode("locked_geom")
                            new_node.add_geom(node.modify_geom(i).decompose().unify(1000000, False))
                            new_geom = NodePath(new_node)
                            new_geom.set_state(state)
                            member_name = "object 0001"
                            member_name = get_unique_name(member_name, obj_names)
                            obj_names.append(member_name)
                            for geom_data in self.__define_locked_geom_data(new_node.get_geom(0),
                                    quadrangulate, gradual):
                                yield
                            member = Mgr.do("create_locked_geom", new_geom,
                                geom_data, materials, member_name).model
                            member.register(restore=False)
                            Mgr.do("add_group_member", member, obj, restore="import")
                            member.bbox.update(new_geom.get_tight_bounds())
                            self._imported_objs.append(member)
                            material = member.get_material()

                            if material and material not in materials:
                                materials.append(material)

                    else:

                        index = geom_indices[0]
                        state = node.get_geom_state(index)
                        tmp_np = node_path.attach_new_node("temp")
                        tmp_np.set_state(state)
                        state = tmp_np.get_net_state()
                        tmp_np.detach_node()
                        new_node = GeomNode("locked_geom")
                        new_node.add_geom(node.modify_geom(index))
                        new_geom = NodePath(new_node)
                        new_geom.set_state(state)
                        new_geom.set_transform(node_path.get_transform())
                        bounds_node = new_geom

                        new_node.decompose()
                        new_node.unify(1000000, False)
                        for geom_data in self.__define_locked_geom_data(new_node.get_geom(0),
                                quadrangulate, gradual):
                            yield
                        obj = Mgr.do("create_locked_geom", new_geom,
                            geom_data, materials, obj_name).model
                        obj.register(restore=False)
                        material = obj.get_material()

                        if material and material not in materials:
                            materials.append(material)

                elif node_type == "CollisionNode":

                    coll_objs = []
                    coll_polys = []
                    coll_planes = []
                    obj_names = GD["obj_names"] + self._obj_names

                    for solid in node.solids:

                        obj_type = solid.type.name

                        if obj_type not in ("CollisionSphere", "CollisionInvSphere", "CollisionCapsule",
                                            "CollisionBox", "CollisionPlane", "CollisionPolygon"):
                            continue

                        if obj_type == "CollisionPolygon":

                            if solid.valid:
                                poly = tuple(solid.points)
                                coll_polys.append(poly)

                        elif obj_type == "CollisionPlane":

                            coll_planes.append(solid.plane)

                        else:

                            name = "object 0001"
                            name = get_unique_name(name, obj_names)
                            obj_names.append(name)

                            if obj_type in ("CollisionSphere", "CollisionInvSphere"):

                                radius = solid.radius
                                pos = solid.center
                                args = (name, radius, pos)

                            elif obj_type == "CollisionCapsule":

                                radius = solid.radius
                                a = solid.point_a
                                b = solid.point_b
                                height_vec = V3D(b - a)
                                height = height_vec.length()
                                hpr = height_vec.get_hpr()
                                args = (name, radius, height, a, hpr)

                            elif obj_type == "CollisionBox":

                                pos = Point3(solid.center)
                                size = {"x": 0., "y": 0., "z": 0.}

                                for i in range(6):
                                    plane = solid.get_plane(i)
                                    x, y, z = plane.get_normal()
                                    dist = abs(plane.dist_to_plane(pos))
                                    size["x" if abs(x) else ("y" if abs(y) else "z")] = dist * 2.

                                x = size["x"]
                                y = size["y"]
                                z = size["z"]
                                pos += Vec3.up() * z * -.5
                                args = (name, x, y, z, pos)

                            coll_objs.append(self.__create_collision_primitive(obj_type, *args))

                    self._imported_objs.extend(coll_objs)

                    if coll_polys:

                        name = "object 0001"
                        name = get_unique_name(name, obj_names)
                        obj_names.append(name)

                        for model in self.__create_collision_model(name, coll_polys, gradual):
                            yield

                        coll_objs.append(model)
                        self._imported_objs.append(model)

                    if coll_planes:
                        plane_models = self.__create_collision_planes(coll_planes, obj_names)
                        coll_objs.extend(plane_models)
                        self._imported_objs.extend(plane_models)

                    if not coll_objs:
                        continue

                    obj = self.__create_collision_group(obj_name, node_path.get_transform())
                    Mgr.do("add_group_members", coll_objs, obj, add_to_hist=False, restore="import")

                else:

                    obj = self.__create_point_helper(obj_name, node_path.get_transform())

                obj.tags = {key: node.get_tag(key) for key in node.get_tag_keys()}
                obj.restore_link(parent_id, None)

                if obj.type == "model":
                    obj.bbox.update(bounds_node.get_tight_bounds())

                self._imported_objs.append(obj)
                obj_id = obj.id
                self._obj_names.remove(obj_name)

            child_indices = node_data["child_indices"]

            for child_index in child_indices:
                if child_index in hierarchy:
                    child_data = hierarchy[child_index]
                    data.append((child_data, obj_id))

            yield

    def __get_progress_steps(self):

        progress_steps = 0
        hierarchy = self._hierarchy

        for index in self._geom_obj_indices:

            node_data = hierarchy[index]
            node = node_data["node_path"].node()

            face_count = 0

            for geom in node.get_geoms():
                for prim in geom.primitives:
                    face_count += prim.get_num_faces()

            n = 7. if hierarchy["quadrangulate"] else 10.
            progress_steps += int(face_count / n)

        for index in self._coll_obj_indices:

            node_data = hierarchy[index]
            node = node_data["node_path"].node()

            coll_poly_count = 0

            for solid in node.solids:
                if solid.type.name == "CollisionPolygon" and solid.is_valid():
                    coll_poly_count += 1

            progress_steps += coll_poly_count // 20

        return progress_steps

    def __import(self):

        progress_steps = self.__get_progress_steps()
        gradual = progress_steps > 80

        yield True

        if gradual:
            Mgr.update_remotely("screenshot", "create")
            GD["progress_steps"] = progress_steps

        Mgr.do("update_history_time")

        for _ in self.__import_objects(gradual):
            if gradual:
                yield True

        self._model_root.detach_node()
        self._model_root = None
        self._hierarchy = {"quadrangulate": False}
        self._obj_index = 0
        self._geom_obj_indices = []
        self._coll_obj_indices = []
        self._imported_file_type = ""
        self._imported_materials = []

        if not self._imported_objs:
            yield False

        # make undo/redoable

        obj_data = {}
        event_data = {"objects": obj_data}
        event_descr = f'Import "{os.path.basename(self._imported_file)}"'
        self._imported_file = ""

        for obj in self._imported_objs:
            obj_data[obj.id] = obj.get_data_to_store("creation")

        self._imported_objs = []
        event_data["object_ids"] = set(Mgr.get("object_ids"))
        Mgr.do("add_history", event_descr, event_data, update_time_id=False)

        yield False

    def __cancel_import_process(self, info):

        if info == "import":

            for obj in self._imported_objs:
                obj.destroy(unregister=False, add_to_hist=False)

            self._model_root.detach_node()
            self._model_root = None
            self._hierarchy = {"quadrangulate": False}
            self._obj_index = 0
            self._geom_obj_indices = []
            self._coll_obj_indices = []
            self._obj_names = []
            self._imported_file = ""
            self._imported_file_type = ""
            self._imported_materials = []
            self._imported_objs = []
            Mgr.do("clear_added_history")

    def __start_import(self):

        Mgr.do("create_material_registry_backup")
        Mgr.do("create_registry_backups")
        Mgr.do("create_id_range_backups")
        do_import = False
        process = self.__import()

        for step in process:
            if step:
                do_import = True
                break

        if do_import and next(process):
            handler = self.__cancel_import_process
            Mgr.add_notification_handler("long_process_cancelled", "import_mgr", handler, once=True)
            task = lambda: Mgr.remove_notification_handler("long_process_cancelled", "import_mgr")
            task_id = "remove_notification_handler"
            PendingTasks.add(task, task_id, "object", id_prefix="import_mgr", sort=100)
            descr = "Importing..."
            Mgr.do_gradually(process, "import", descr, cancellable=True)

    def __update_import(self, update_type, *args):

        if update_type == "prepare":
            self.__prepare_import(*args)
        elif update_type == "cancel":
            self.__cancel_import()
        elif update_type == "start":
            self.__start_import()


MainObjects.add_class(ImportManager)
