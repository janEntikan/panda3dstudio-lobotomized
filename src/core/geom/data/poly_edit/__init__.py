from ....basis import *
from .create import CreationMixin, CreationManager
from .triangulate import TriangulationMixin, TriangulationManager
from .smooth import SmoothingMixin, SmoothingManager, SmoothingGroup
from .surface import SurfaceMixin, SurfaceManager
from .extrusion_inset import ExtrusionInsetMixin, ExtrusionInsetManager


class PolygonEditMixin(CreationMixin, TriangulationMixin, SmoothingMixin,
                       SurfaceMixin, ExtrusionInsetMixin):
    """ GeomDataObject class mix-in """

    def __init__(self):

        TriangulationMixin.__init__(self)
        SmoothingMixin.__init__(self)

    def update_poly_centers(self):

        for poly in self.ordered_polys:
            poly.update_center_pos()

    def update_poly_normals(self):

        for poly in self.ordered_polys:
            poly.update_normal()

    def detach_polygons(self):

        selected_poly_ids = self._selected_subobj_ids["poly"]

        if not selected_poly_ids:
            return False

        merged_edges = self.merged_edges
        polys = self._subobjs["poly"]
        selected_polys = (polys[i] for i in selected_poly_ids)
        border_edges = []

        for poly in selected_polys:

            for edge_id in poly.edge_ids:

                merged_edge = merged_edges[edge_id]

                if merged_edge in border_edges:
                    border_edges.remove(merged_edge)
                else:
                    border_edges.append(merged_edge)

        edge_ids = set(e_id for merged_edge in border_edges for e_id in merged_edge)

        return self.split_edges(edge_ids)

    def set_subobjs_to_unregister(self, polys_to_unreg):

        verts_to_unreg = []
        edges_to_unreg = []
        subobjs_to_unreg = {"vert": {}, "edge": {}, "poly": {}}

        for poly in polys_to_unreg:
            verts_to_unreg.extend(poly.vertices)
            edges_to_unreg.extend(poly.edges)
            subobjs_to_unreg["poly"][poly.id] = poly

        for vert in verts_to_unreg:
            subobjs_to_unreg["vert"][vert.id] = vert

        for edge in edges_to_unreg:
            subobjs_to_unreg["edge"][edge.id] = edge

        self._subobjs_to_unreg = subobjs_to_unreg

    def delete_polygons(self, polys_to_delete, unregister_globally=True, unregister_locally=True):

        subobjs = self._subobjs
        verts = subobjs["vert"]
        edges = subobjs["edge"]
        polys = subobjs["poly"]
        ordered_polys = self.ordered_polys

        selected_subobj_ids = self._selected_subobj_ids
        selected_vert_ids = selected_subobj_ids["vert"]
        selected_edge_ids = selected_subobj_ids["edge"]
        selected_poly_ids = selected_subobj_ids["poly"]
        selected_normal_ids = selected_subobj_ids["normal"]
        self._verts_to_transf["vert"] = {}
        self._verts_to_transf["edge"] = {}
        self._verts_to_transf["poly"] = {}
        verts_to_delete = []
        edges_to_delete = []
        border_edges = []

        poly_index = min(ordered_polys.index(poly) for poly in polys_to_delete)
        polys_to_offset = ordered_polys[poly_index:]

        merged_verts = self.merged_verts
        merged_edges = self.merged_edges
        shared_normals = self.shared_normals
        locked_normals = self.locked_normals
        row_ranges_to_keep = SparseArray()
        row_ranges_to_keep.set_range(0, self._data_row_count)

        subobjs_to_unreg = {"vert": {}, "edge": {}, "poly": {}}

        subobj_change = self._subobj_change
        subobj_change["vert"]["deleted"] = vert_change = {}
        subobj_change["edge"]["deleted"] = edge_change = {}
        subobj_change["poly"]["deleted"] = poly_change = {}

        for poly in polys_to_delete:

            poly_verts = poly.vertices
            vert = poly_verts[0]
            row = vert.row_index
            row_ranges_to_keep.clear_range(row, len(poly_verts))

            verts_to_delete.extend(poly_verts)
            edges_to_delete.extend(poly.edges)

            for edge_id in poly.edge_ids:

                merged_edge = merged_edges[edge_id]

                if merged_edge in border_edges:
                    border_edges.remove(merged_edge)
                else:
                    border_edges.append(merged_edge)

            ordered_polys.remove(poly)
            poly_id = poly.id
            subobjs_to_unreg["poly"][poly_id] = poly
            poly_change[poly] = poly.creation_time

            if poly_id in selected_poly_ids:
                selected_poly_ids.remove(poly_id)

        merged_verts_to_resmooth = set()

        for vert in verts_to_delete:

            vert_id = vert.id
            subobjs_to_unreg["vert"][vert_id] = vert
            vert_change[vert] = vert.creation_time

            if vert_id in selected_vert_ids:
                selected_vert_ids.remove(vert_id)

            if vert_id in selected_normal_ids:
                selected_normal_ids.remove(vert_id)

            if vert_id in merged_verts:
                merged_vert = merged_verts[vert_id]
                merged_vert.remove(vert_id)
                del merged_verts[vert_id]
                merged_verts_to_resmooth.add(merged_vert)

            if vert_id in shared_normals:
                shared_normal = shared_normals[vert_id]
                shared_normal.discard(vert_id)
                del shared_normals[vert_id]

            locked_normals.discard(vert_id)

        for edge in edges_to_delete:

            edge_id = edge.id
            subobjs_to_unreg["edge"][edge_id] = edge
            edge_change[edge] = edge.creation_time

            if edge_id in selected_edge_ids:
                selected_edge_ids.remove(edge_id)

            if edge_id in merged_edges:

                merged_edge = merged_edges[edge_id]
                merged_edge.remove(edge_id)
                del merged_edges[edge_id]

                if not merged_edge[:] and merged_edge in border_edges:
                    border_edges.remove(merged_edge)

        if border_edges:

            new_merged_verts = self.fix_borders(border_edges)

            if new_merged_verts:
                self.update_normal_sharing(new_merged_verts)
                merged_verts_to_resmooth.update(new_merged_verts)

        if unregister_globally:
            self._subobjs_to_unreg = subobjs_to_unreg
            self.unregister(locally=unregister_locally)
        elif unregister_locally:
            self.unregister_locally(subobjs_to_unreg)

        row_index_offset = 0

        for poly in polys_to_offset:

            if poly in polys_to_delete:
                row_index_offset -= poly.vertex_count
                continue

            for vert in poly.vertices:
                vert.offset_row_index(row_index_offset)

        sel_data = self._poly_selection_data
        geoms = self._geoms

        for state in ("selected", "unselected"):
            sel_data[state] = []
            prim = geoms["poly"][state].node().modify_geom(0).modify_primitive(0)
            prim.modify_vertices().clear_rows()

        vert_geom = geoms["vert"]["pickable"].node().modify_geom(0)
        edge_geom = geoms["edge"]["pickable"].node().modify_geom(0)
        normal_geom = geoms["normal"]["pickable"].node().modify_geom(0)
        vertex_data_vert = vert_geom.modify_vertex_data()
        vertex_data_edge = edge_geom.modify_vertex_data()
        vertex_data_normal = normal_geom.modify_vertex_data()
        vertex_data_poly = self._vertex_data["poly"]
        vertex_data_poly_picking = self._vertex_data["poly_picking"]

        vert_array = vertex_data_vert.modify_array(1)
        vert_view = memoryview(vert_array).cast("B")
        vert_stride = vert_array.array_format.stride
        edge_array = vertex_data_edge.modify_array(1)
        edge_view = memoryview(edge_array).cast("B")
        edge_stride = edge_array.array_format.stride
        picking_array = vertex_data_poly_picking.modify_array(1)
        picking_view = memoryview(picking_array).cast("B")
        picking_stride = picking_array.array_format.stride

        poly_arrays = []
        poly_views = []
        poly_strides = []

        for i in range(vertex_data_poly.get_num_arrays()):
            poly_array = vertex_data_poly.modify_array(i)
            poly_arrays.append(poly_array)
            poly_views.append(memoryview(poly_array).cast("B"))
            poly_strides.append(poly_array.array_format.stride)

        pos_array = poly_arrays[0]
        f = lambda values, stride: (v * stride for v in values)
        offset = 0

        for i in range(row_ranges_to_keep.get_num_subranges()):

            start = row_ranges_to_keep.get_subrange_begin(i)
            size = row_ranges_to_keep.get_subrange_end(i) - start
            offset_, start_, size_ = f((offset, start, size), vert_stride)
            vert_view[offset_:offset_+size_] = vert_view[start_:start_+size_]
            offset_, start_, size_ = f((offset, start, size), edge_stride)
            edge_view[offset_:offset_+size_] = edge_view[start_:start_+size_]
            offset_, start_, size_ = f((offset, start, size), picking_stride)
            picking_view[offset_:offset_+size_] = picking_view[start_:start_+size_]

            for poly_view, poly_stride in zip(poly_views, poly_strides):
                offset_, start_, size_ = f((offset, start, size), poly_stride)
                poly_view[offset_:offset_+size_] = poly_view[start_:start_+size_]

            offset += size

        old_count = self._data_row_count
        count = len(verts)
        offset = count

        for i in range(row_ranges_to_keep.get_num_subranges()):
            start = row_ranges_to_keep.get_subrange_begin(i)
            size = row_ranges_to_keep.get_subrange_end(i) - start
            offset_, start_, size_ = f((offset, start + old_count, size), edge_stride)
            edge_view[offset_:offset_+size_] = edge_view[start_:start_+size_]
            offset += size

        self._data_row_count = count
        sel_colors = Mgr.get("subobj_selection_colors")

        vertex_data_poly.set_num_rows(count)
        vertex_data_vert.set_num_rows(count)
        vertex_data_vert.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_normal.set_num_rows(count)
        vertex_data_poly_picking.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_normal.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_normal.set_array(1, GeomVertexArrayData(vert_array))
        vertex_data_normal.set_array(2, GeomVertexArrayData(poly_arrays[2]))

        vertex_data_vert = geoms["vert"]["sel_state"].node().modify_geom(0).modify_vertex_data()
        vertex_data_vert.set_num_rows(count)
        vertex_data_vert.set_array(0, GeomVertexArrayData(pos_array))
        new_data = vertex_data_vert.set_color(sel_colors["vert"]["unselected"])
        vertex_data_vert.set_array(1, new_data.get_array(1))

        vertex_data_normal = geoms["normal"]["sel_state"].node().modify_geom(0).modify_vertex_data()
        vertex_data_normal.set_num_rows(count)
        vertex_data_normal.set_array(0, GeomVertexArrayData(pos_array))
        new_data = vertex_data_normal.set_color(sel_colors["normal"]["unselected"])
        vertex_data_normal.set_array(1, new_data.get_array(1))
        vertex_data_normal.set_array(2, GeomVertexArrayData(poly_arrays[2]))

        size = pos_array.data_size_bytes
        from_view = memoryview(pos_array).cast("B")

        vertex_data_edge.set_num_rows(count * 2)
        pos_array_edge = vertex_data_edge.modify_array(0)
        to_view = memoryview(pos_array_edge).cast("B")
        to_view[:size] = from_view
        to_view[size:] = from_view

        vertex_data_edge = geoms["edge"]["sel_state"].node().modify_geom(0).modify_vertex_data()
        vertex_data_edge.set_num_rows(count * 2)
        pos_array_edge = vertex_data_edge.modify_array(0)
        to_view = memoryview(pos_array_edge).cast("B")
        to_view[:size] = from_view
        to_view[size:] = from_view
        new_data = vertex_data_edge.set_color(sel_colors["edge"]["unselected"])
        vertex_data_edge.set_array(1, new_data.get_array(1))

        data_unselected = sel_data["unselected"]

        for poly in ordered_polys:
            data_unselected.extend(poly)

        points_prim = GeomPoints(Geom.UH_static)
        points_prim.set_index_type(Geom.NT_uint32)
        points_prim.reserve_num_vertices(count)
        points_prim.add_next_vertices(count)
        vert_geom.set_primitive(0, points_prim)
        normal_geom.set_primitive(0, GeomPoints(points_prim))
        geom_node = geoms["vert"]["sel_state"].node()
        geom_node.modify_geom(0).set_primitive(0, GeomPoints(points_prim))
        geom_node = geoms["normal"]["sel_state"].node()
        geom_node.modify_geom(0).set_primitive(0, GeomPoints(points_prim))

        lines_prim = GeomLines(Geom.UH_static)
        lines_prim.set_index_type(Geom.NT_uint32)
        lines_prim.reserve_num_vertices(count * 2)

        tris_prim = GeomTriangles(Geom.UH_static)
        tris_prim.set_index_type(Geom.NT_uint32)

        for poly in ordered_polys:

            for edge in poly.edges:
                row1, row2 = edge.row_indices
                lines_prim.add_vertices(row1, row2)

            for vert_ids in poly:
                tris_prim.add_vertices(*[verts[v_id].row_index for v_id in vert_ids])

        edge_geom.set_primitive(0, lines_prim)
        geom_node = geoms["edge"]["sel_state"].node()
        geom_node.modify_geom(0).set_primitive(0, GeomLines(lines_prim))

        geom_node_top = self._toplvl_node
        geom_node_top.modify_geom(0).set_primitive(0, tris_prim)

        geom_node = geoms["poly"]["unselected"].node()
        geom_node.modify_geom(0).set_primitive(0, GeomTriangles(tris_prim))

        geom_node = geoms["poly"]["pickable"].node()
        geom_node.modify_geom(0).set_primitive(0, GeomTriangles(tris_prim))

        vertex_data_top = geom_node_top.modify_geom(0).modify_vertex_data()

        for i, poly_array in enumerate(poly_arrays):
            vertex_data_top.set_array(i, poly_array)

        geom_node.modify_geom(0).set_primitive(0, GeomTriangles(tris_prim))

        for subobj_type in ("vert", "edge", "poly", "normal"):
            selected_subobj_ids[subobj_type] = []

        if selected_vert_ids:
            selected_verts = (verts[vert_id] for vert_id in selected_vert_ids)
            self.update_selection("vert", selected_verts, [])

        if selected_edge_ids:
            selected_edges = (edges[edge_id] for edge_id in selected_edge_ids)
            self.update_selection("edge", selected_edges, [])

        if selected_poly_ids:
            selected_polys = (polys[poly_id] for poly_id in selected_poly_ids)
            self.update_selection("poly", selected_polys, [])

        if selected_normal_ids:
            selected_normals = set(shared_normals[normal_id] for normal_id in selected_normal_ids)
            self.update_selection("normal", selected_normals, [])

        self.update_locked_normal_selection(None, None, locked_normals, [])
        self.update_subobject_indices()

        poly_ids = [poly.id for poly in polys_to_delete]
        self.smooth_polygons(poly_ids, smooth=False, update_normals=False)
        self._normal_sharing_change = True
        self.update_vertex_normals(merged_verts_to_resmooth)
        self.toplevel_obj.bbox.update(self.origin.get_tight_bounds())

    def create_new_geometry(self, new_polys, create_normals=True):

        new_verts = []
        new_edges = []

        for poly in new_polys:
            new_verts.extend(poly.vertices)
            new_edges.extend(poly.edges)

        merged_verts = self.merged_verts
        merged_edges = self.merged_edges
        locked_normals = self.locked_normals
        subobjs = self._subobjs
        verts = subobjs["vert"]
        edges = subobjs["edge"]
        polys = subobjs["poly"]
        indexed_subobjs = self._indexed_subobjs
        indexed_verts = indexed_subobjs["vert"]
        indexed_edges = indexed_subobjs["edge"]
        indexed_polys = indexed_subobjs["poly"]
        selection_ids = self._selected_subobj_ids
        selected_vert_ids = selection_ids["vert"]
        selected_edge_ids = selection_ids["edge"]

        Mgr.do("register_vert_objs", new_verts, restore=False)
        Mgr.do("register_edge_objs", new_edges, restore=False)
        Mgr.do("register_poly_objs", new_polys, restore=False)

        subobj_change = self._subobj_change
        subobj_change["vert"].setdefault("created", []).extend(new_verts)
        subobj_change["edge"].setdefault("created", []).extend(new_edges)
        subobj_change["poly"].setdefault("created", []).extend(new_polys)

        normal_change = self._normal_change
        normal_lock_change = self._normal_lock_change

        vert_ids_to_add = set()
        edge_ids_to_add = set(selected_edge_ids)

        for vert in new_verts:

            if vert.has_locked_normal():
                locked_normals.add(vert.id)

            normal_change.add(vert.id)
            normal_lock_change.add(vert.id)
            id_set = set(merged_verts[vert.id])

            if not (id_set.isdisjoint(selected_vert_ids) or id_set.issubset(selected_vert_ids)):
                vert_ids_to_add.update(id_set.difference(selected_vert_ids))

        for edge in new_edges:

            id_set = set(merged_edges[edge.id])

            if not (id_set.isdisjoint(selected_edge_ids) or id_set.issubset(selected_edge_ids)):
                edge_ids_to_add.update(id_set.difference(selected_edge_ids))

        if create_normals:

            shared_normals = self.shared_normals

            for vert in new_verts:
                shared_normals[vert.id] = Mgr.do("create_shared_normal", self, [vert.id])

        self.clear_selection("edge", update_verts_to_transf=False)

        # Update geometry structures

        vert_count = sum([poly.vertex_count for poly in new_polys])
        old_count = self._data_row_count
        count = old_count + vert_count
        self._data_row_count = count

        geoms = self._geoms
        geom_node_top = self._toplvl_node
        vertex_data_top = geom_node_top.modify_geom(0).modify_vertex_data()
        vertex_data_top.reserve_num_rows(count)
        vertex_data_poly_picking = self._vertex_data["poly_picking"]
        vertex_data_poly_picking.reserve_num_rows(count)
        vertex_data_poly_picking.set_num_rows(count)

        pos_writer = GeomVertexWriter(vertex_data_top, "vertex")
        pos_writer.set_row(old_count)
        col_writer = GeomVertexWriter(vertex_data_poly_picking, "color")
        col_writer.set_row(old_count)
        ind_writer_poly = GeomVertexWriter(vertex_data_poly_picking, "index")
        ind_writer_poly.set_row(old_count)
        normal_writer = GeomVertexWriter(vertex_data_top, "normal")
        normal_writer.set_row(old_count)

        poly_type_id = PickableTypes.get_id("poly")

        prev_count = old_count
        verts_by_row = {}
        poly_picking_colors = {}
        poly_indices = {}
        poly_index = len(polys)
        sel_data = self._poly_selection_data["unselected"]
        sign = -1. if self.owner.has_inverted_geometry() else 1.

        for poly in new_polys:

            for i, vert in enumerate(poly.vertices):
                vert.row_index = i
                vert.offset_row_index(prev_count)
                verts_by_row[vert.row_index] = vert

            prev_count += poly.vertex_count

            picking_col_id = poly.picking_color_id
            picking_color = get_color_vec(picking_col_id, poly_type_id)
            poly_picking_colors[poly.id] = picking_color
            poly_indices[poly.id] = poly_index
            indexed_polys[poly_index] = poly
            poly_index += 1
            sel_data.extend(poly)

        for row in sorted(verts_by_row):
            vert = verts_by_row[row]
            pos = vert.get_pos()
            pos_writer.add_data3(pos)
            picking_color = poly_picking_colors[vert.polygon_id]
            col_writer.add_data4(picking_color)
            poly_index = poly_indices[vert.polygon_id]
            ind_writer_poly.add_data1i(poly_index)
            normal = vert.normal
            normal_writer.add_data3(normal * sign)

        vertex_data_vert1 = geoms["vert"]["pickable"].node().modify_geom(0).modify_vertex_data()
        vertex_data_vert1.set_num_rows(count)
        vertex_data_vert2 = geoms["vert"]["sel_state"].node().modify_geom(0).modify_vertex_data()
        vertex_data_vert2.set_num_rows(count)
        vertex_data_normal1 = geoms["normal"]["pickable"].node().modify_geom(0).modify_vertex_data()
        vertex_data_normal1.set_num_rows(count)
        vertex_data_normal2 = geoms["normal"]["sel_state"].node().modify_geom(0).modify_vertex_data()
        vertex_data_normal2.set_num_rows(count)
        col_writer1 = GeomVertexWriter(vertex_data_vert1, "color")
        col_writer1.set_row(old_count)
        col_writer2 = GeomVertexWriter(vertex_data_vert2, "color")
        col_writer2.set_row(old_count)
        col_writer3 = GeomVertexWriter(vertex_data_normal2, "color")
        col_writer3.set_row(old_count)
        ind_writer_vert = GeomVertexWriter(vertex_data_vert1, "index")
        ind_writer_vert.set_row(old_count)

        sel_colors = Mgr.get("subobj_selection_colors")
        color_vert = sel_colors["vert"]["unselected"]
        color_normal = sel_colors["normal"]["unselected"]
        vert_type_id = PickableTypes.get_id("vert")

        for row in sorted(verts_by_row):
            vert = verts_by_row[row]
            picking_color = get_color_vec(vert.picking_color_id, vert_type_id)
            col_writer1.add_data4(picking_color)
            col_writer2.add_data4(color_vert)
            col_writer3.add_data4(color_normal)
            ind_writer_vert.add_data1i(row)
            indexed_verts[row] = vert

        col_array = GeomVertexArrayData(vertex_data_vert1.get_array(1))
        vertex_data_normal1.set_array(1, col_array)

        picking_colors1 = {}
        picking_colors2 = {}
        edge_type_id = PickableTypes.get_id("edge")
        indices1 = {}
        indices2 = {}
        edge_index = len(edges)

        for edge in new_edges:
            row1, row2 = [verts[v_id].row_index for v_id in edge]
            picking_color = get_color_vec(edge.picking_color_id, edge_type_id)
            picking_colors1[row1] = picking_color
            picking_colors2[row2 + count] = picking_color
            indices1[row1] = edge_index
            indices2[row2 + count] = edge_index
            indexed_edges[edge_index] = edge
            edge_index += 1

        vertex_data_edge1 = geoms["edge"]["pickable"].node().modify_geom(0).modify_vertex_data()
        vertex_data_edge2 = geoms["edge"]["sel_state"].node().modify_geom(0).modify_vertex_data()
        vertex_data_edge2.set_num_rows(count * 2)
        vertex_data_tmp = GeomVertexData(vertex_data_edge1)
        vertex_data_tmp.set_num_rows(count)
        col_writer1 = GeomVertexWriter(vertex_data_tmp, "color")
        col_writer1.set_row(old_count)
        col_writer2 = GeomVertexWriter(vertex_data_edge2, "color")
        col_writer2.set_row(old_count)
        ind_writer_edge = GeomVertexWriter(vertex_data_tmp, "index")
        ind_writer_edge.set_row(old_count)
        color = sel_colors["edge"]["unselected"]

        for row_index in sorted(picking_colors1):
            picking_color = picking_colors1[row_index]
            col_writer1.add_data4(picking_color)
            col_writer2.add_data4(color)
            ind_writer_edge.add_data1i(indices1[row_index])

        from_array = vertex_data_tmp.get_array(1)
        size = from_array.data_size_bytes
        from_view = memoryview(from_array).cast("B")

        vertex_data_tmp = GeomVertexData(vertex_data_edge1)
        stride = vertex_data_tmp.get_array(1).array_format.stride
        vertex_data_tmp.set_num_rows(old_count + count)
        col_writer1 = GeomVertexWriter(vertex_data_tmp, "color")
        col_writer1.set_row(old_count * 2)
        col_writer2.set_row(old_count + count)
        ind_writer_edge = GeomVertexWriter(vertex_data_tmp, "index")
        ind_writer_edge.set_row(old_count * 2)

        for row_index in sorted(picking_colors2):
            picking_color = picking_colors2[row_index]
            col_writer1.add_data4(picking_color)
            col_writer2.add_data4(color)
            ind_writer_edge.add_data1i(indices2[row_index])

        vertex_data_edge1.set_num_rows(count * 2)
        to_array = vertex_data_edge1.modify_array(1)
        to_view = memoryview(to_array).cast("B")
        to_view[:size] = from_view

        from_array = vertex_data_tmp.get_array(1)
        from_view = memoryview(from_array).cast("B")
        to_view[size:] = from_view[-size:]

        lines_prim = GeomLines(Geom.UH_static)
        lines_prim.set_index_type(Geom.NT_uint32)
        lines_prim.reserve_num_vertices(count * 2)

        for poly in self.ordered_polys:
            for edge in poly.edges:
                row1, row2 = [verts[v_id].row_index for v_id in edge]
                lines_prim.add_vertices(row1, row2 + count)

        geom_node = geoms["edge"]["pickable"].node()
        geom_node.modify_geom(0).set_primitive(0, lines_prim)
        geom_node = geoms["edge"]["sel_state"].node()
        geom_node.modify_geom(0).set_primitive(0, GeomLines(lines_prim))

        vertex_data_poly = self._vertex_data["poly"]
        vertex_data_poly.set_num_rows(count)

        vertex_data_top = geom_node_top.get_geom(0).get_vertex_data()
        pos_array = vertex_data_top.get_array(0)
        size = pos_array.data_size_bytes
        from_view = memoryview(pos_array).cast("B")
        normal_array = vertex_data_top.get_array(2)
        tan_array = vertex_data_top.get_array(3)
        vertex_data_poly_picking.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_vert1.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_vert2.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_normal1.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_normal2.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_normal1.set_array(2, GeomVertexArrayData(normal_array))
        vertex_data_normal2.set_array(2, GeomVertexArrayData(normal_array))
        vertex_data_poly.set_array(0, GeomVertexArrayData(pos_array))
        vertex_data_poly.set_array(2, GeomVertexArrayData(normal_array))
        vertex_data_poly.set_array(3, GeomVertexArrayData(tan_array))
        pos_array_edge = GeomVertexArrayData(pos_array.array_format, pos_array.usage_hint)
        pos_array_edge.unclean_set_num_rows(pos_array.get_num_rows() * 2)
        to_view = memoryview(pos_array_edge).cast("B")
        to_view[:size] = from_view
        to_view[size:] = from_view
        vertex_data_edge1.set_array(0, pos_array_edge)
        vertex_data_edge2.set_array(0, pos_array_edge)

        tris_prim = geom_node_top.modify_geom(0).modify_primitive(0)

        for poly in new_polys:
            for vert_ids in poly:
                tris_prim.add_vertices(*[verts[v_id].row_index for v_id in vert_ids])

        tris_prim.make_indexed()
        from_array = tris_prim.get_vertices()
        stride = from_array.array_format.stride
        new_row_count = sum([len(poly) for poly in new_polys])
        size = new_row_count * stride
        from_view = memoryview(from_array).cast("B")
        geom_node = geoms["poly"]["unselected"].node()
        prim = geom_node.modify_geom(0).modify_primitive(0)
        to_array = prim.modify_vertices()
        to_size = to_array.data_size_bytes
        to_array.set_num_rows(to_array.get_num_rows() + new_row_count)
        to_view = memoryview(to_array).cast("B")
        to_view[to_size:to_size+size] = from_view[-size:]
        geom_node = geoms["poly"]["pickable"].node()
        prim = geom_node.modify_geom(0).modify_primitive(0)
        to_array = prim.modify_vertices()
        to_size = to_array.data_size_bytes
        to_array.set_num_rows(to_array.get_num_rows() + new_row_count)
        to_view = memoryview(to_array).cast("B")
        to_view[to_size:to_size+size] = from_view[-size:]

        tmp_prim = GeomPoints(Geom.UH_static)
        tmp_prim.set_index_type(Geom.NT_uint32)
        tmp_prim.reserve_num_vertices(vert_count)
        tmp_prim.add_next_vertices(vert_count)
        tmp_prim.offset_vertices(old_count)
        tmp_prim.make_indexed()
        from_array = tmp_prim.get_vertices()
        from_size = from_array.data_size_bytes
        from_view = memoryview(from_array).cast("B")
        geom_node = geoms["vert"]["pickable"].node()
        prim = geom_node.modify_geom(0).modify_primitive(0)
        to_array = prim.modify_vertices()
        to_size = to_array.data_size_bytes
        to_array.set_num_rows(count)
        to_view = memoryview(to_array).cast("B")
        to_view[to_size:to_size+from_size] = from_view
        geom_node = geoms["vert"]["sel_state"].node()
        prim = geom_node.modify_geom(0).modify_primitive(0)
        to_array = prim.modify_vertices()
        to_size = to_array.data_size_bytes
        to_array.set_num_rows(count)
        to_view = memoryview(to_array).cast("B")
        to_view[to_size:to_size+from_size] = from_view
        geom_node = geoms["normal"]["pickable"].node()
        geom_node.modify_geom(0).set_primitive(0, GeomPoints(prim))
        geom_node = geoms["normal"]["sel_state"].node()
        geom_node.modify_geom(0).set_primitive(0, GeomPoints(prim))

        if vert_ids_to_add:
            # since update_selection(...) processes *all* subobjects referenced by the
            # merged subobject, it is replaced by a temporary merged subobject that
            # only references newly created subobjects;
            # as an optimization, one temporary merged subobject references all newly
            # created subobjects, so self.update_selection() needs to be called only
            # once
            tmp_merged_vert = Mgr.do("create_merged_vert", self)
            tmp_merged_vert.extend(vert_ids_to_add)
            vert_id = tmp_merged_vert.id
            orig_merged_vert = merged_verts[vert_id]
            merged_verts[vert_id] = tmp_merged_vert
            self.update_selection("vert", [tmp_merged_vert], [], False)
            # the original merged subobject can now be restored
            merged_verts[vert_id] = orig_merged_vert

        if edge_ids_to_add:
            tmp_merged_edge = Mgr.do("create_merged_edge", self)
            tmp_merged_edge.extend(edge_ids_to_add)
            edge_id = tmp_merged_edge.id
            orig_merged_edge = merged_edges[edge_id]
            merged_edges[edge_id] = tmp_merged_edge
            self.update_selection("edge", [tmp_merged_edge], [], False)
            merged_edges[edge_id] = orig_merged_edge

        self._update_verts_to_transform("vert")
        self._update_verts_to_transform("edge")
        self._update_verts_to_transform("poly")
        self._normal_sharing_change = True
        self.origin.node().set_bounds(geom_node_top.get_bounds())
        model = self.toplevel_obj
        model.bbox.update(self.origin.get_tight_bounds())

        if model.has_tangent_space():
            tangent_flip, bitangent_flip = model.get_tangent_space_flip()
            self.update_tangent_space(tangent_flip, bitangent_flip, [p.id for p in new_polys])
        else:
            self.is_tangent_space_initialized = False


class PolygonEditManager(CreationManager, TriangulationManager, SmoothingManager,
                         SurfaceManager, ExtrusionInsetManager):

    def __init__(self):

        CreationManager.__init__(self)
        TriangulationManager.__init__(self)
        SmoothingManager.__init__(self)
        SurfaceManager.__init__(self)
        ExtrusionInsetManager.__init__(self)

        self._pixel_under_mouse = None

        Mgr.add_app_updater("poly_detach", self.__detach_polygons)

    def __detach_polygons(self):

        # exit any subobject modes
        Mgr.exit_states(min_persistence=-99)
        selection = Mgr.get("selection_top")
        changed_objs = {}

        for model in selection:

            geom_data_obj = model.geom_obj.geom_data_obj

            if geom_data_obj.detach_polygons():
                changed_objs[model.id] = geom_data_obj

        if not changed_objs:
            return

        Mgr.do("update_history_time")
        obj_data = {}

        for obj_id, geom_data_obj in changed_objs.items():
            obj_data[obj_id] = geom_data_obj.get_data_to_store("prop_change", "subobj_merge")

        event_descr = "Detach polygon selection"
        event_data = {"objects": obj_data}
        Mgr.do("add_history", event_descr, event_data, update_time_id=False)

    def _update_cursor(self, task):

        pixel_under_mouse = Mgr.get("pixel_under_mouse")

        if self._pixel_under_mouse != pixel_under_mouse:
            Mgr.set_cursor("main" if pixel_under_mouse == VBase4() else "select")
            self._pixel_under_mouse = pixel_under_mouse

        return task.cont


MainObjects.add_class(PolygonEditManager)
