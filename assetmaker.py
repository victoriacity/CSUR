import os, shutil, json
import xmlserializer
import assets
from copy import deepcopy
from modeler import ModelerLodded
import csur
from csur import Segment
from csur import StandardWidth as SW
from thumbnail import draw
import prop_utils

class AssetMaker:

    connectgroup = {'None': 'None', '11': 'WideTram', '33': 'SingleTram', '31': 'NarrowTram',
                    '3-1': 'DoubleTrain', '00': 'CenterTram', '1-1': 'SingleTrain', 'other': 'DoubleMonorail'}
    connectgroup_side = {2: "", 5: "TrainStation", 7: "SingleMonorail", 9: "MonorailStation"}
    

    # note: metro mode is used to visualize underground construction
    names = {'g': 'basic', 'e': 'elevated', 'b': 'bridge', 't': 'tunnel', 's': 'slope'}
    shaders = {'g': 'Road', 'e': 'RoadBridge', 'b': 'RoadBridge', 't': 'RoadBridge', 's': 'RoadBridge'}
    suffix = {'e': 'express', 'w': 'weave', 'c': 'compact', 'p': 'parking'}
    
    segment_presets = {}
    node_presets = {}
    lanes = {}
    props = {}

    def __init__(self, dir, config_file='csur_blender.ini',
                 template_path='templates', output_path='output', bridge=False, tunnel=True):
        self.modeler = ModelerLodded(os.path.join(dir, config_file), bridge, tunnel, optimize=True)
        self.output_path = os.path.join(dir, output_path)
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)
        self.template_path = os.path.join(dir, template_path)
        self.workdir = dir
        self.bridge = bridge
        self.tunnel = tunnel
        self.assetdata = {}
        self.assets_made = []
        with open(os.path.join(self.template_path, 'segment_presets.json'), 'r') as f:
            self.segment_presets = json.load(f)
        with open(os.path.join(self.template_path, 'node_presets.json'), 'r') as f:
            self.node_presets = json.load(f)
        with open(os.path.join(self.template_path, 'skins.json'), 'r') as f:
            self.skins = json.load(f)
        with open(os.path.join(self.template_path, 'props.json'), 'r') as f:
            self.props = json.load(f)
        self.lanes = {}
        for path in os.listdir(os.path.join(self.template_path, 'lane')):
            with open(os.path.join(self.template_path, 'lane', path), 'r') as f:
                self.lanes[os.path.splitext(path)[0]] = json.load(f)

    def get_connectgroup(self, key):
        if key in AssetMaker.connectgroup:
            return AssetMaker.connectgroup[key]
        else:
            return AssetMaker.connectgroup['other']

    def get_fullname(self, mode):
        if len(mode) > 2:
            raise ValueError("Invalid mode name!")
        return AssetMaker.names[mode[0]] + (AssetMaker.suffix[mode[1]] if len(mode) > 1 else '')
    
    def get_basename(self, mode):
        if len(mode) > 2:
            raise ValueError("Invalid mode name!")
        return AssetMaker.names[mode[0]]

    def __initialize_assetinfo(self, asset):
        self.assetdata = {}
        self.assetdata['name'] = str(asset.get_model('g'))
        for v in AssetMaker.names.values():
            with open(os.path.join(self.template_path, 'netinfo', '%s.json' % v), 'r') as f:
                jsondata = json.load(f)
                self.assetdata[v] = jsondata
            with open(os.path.join(self.template_path, 'net_ai', '%s.json' % v), 'r') as f:
                jsondata = json.load(f)
                self.assetdata['%sAI' % v] = jsondata
            self.assetdata['%sModel' % v] = {'segmentMeshes': {'CSMesh': []}, 'nodeMeshes': {'CSMesh': []}}
        return self.assetdata

    def __create_mesh(self, color, shader, name, tex=None):
        color = {'float': [str(x) for x in color]}
        csmesh = {}
        csmesh['color'] = color
        csmesh['shader'] = 'Custom/Net/%s' % shader
        csmesh['name'] = name
        if tex == 'disabled':
            csmesh['texture'] = ''
        else:
            csmesh['texture'] = tex or name.split('_')[-1]
        return csmesh

    def __add_segment(self, name, model, mode='g', texmode=None, preset='default', color=[0.5, 0.5, 0.5]):
        if type(model) == str:
            # uses saved file if the model is a string
            # path to file should omit .FBX extention 
            shutil.copy(model + '.FBX', os.path.join(self.output_path, name + '.FBX'))
            shutil.copy(model + '_lod.FBX', os.path.join(self.output_path, name + '_lod.FBX'))
        else:    
            self.modeler.save(model, os.path.join(self.output_path, name + '.FBX'))
        modename = self.get_basename(mode)
        texmode = texmode or modename
        if texmode == 'metro':
            newmesh = self.__create_mesh(color, 'Metro', name, 'disabled')
        else:
            newmesh = self.__create_mesh(color, AssetMaker.shaders[mode[0]], name, texmode)
        self.assetdata['%sModel' % modename]['segmentMeshes']['CSMesh'].append(newmesh)
        segmentinfo = deepcopy(self.segment_presets[preset])
        self.assetdata[modename]['m_segments']['Segment'].append(segmentinfo)

    def __add_node(self, name, model, mode='g', texmode=None, preset='default', color=[0.5, 0.5, 0.5], connectgroup=None):
        self.modeler.save(model, os.path.join(self.output_path, name + '.FBX'))
        modename = self.get_basename(mode)
        texmode = texmode or modename
        newmesh = self.__create_mesh(color, AssetMaker.shaders[mode[0]], name, texmode)     
        self.assetdata['%sModel' % modename]['nodeMeshes']['CSMesh'].append(newmesh)
        nodeinfo = deepcopy(self.node_presets[preset])
        self.assetdata[modename]['m_nodes']['Node'].append(nodeinfo)
        if connectgroup:
            self.assetdata[modename]['m_nodes']['Node'][-1]['m_connectGroup'] = connectgroup

    def __create_segment(self, asset, mode):
        modename = self.get_fullname(mode)
        seg = asset.get_model(mode)
        name = self.assetdata['name']
        # make model
        seg_lanes, seg_struc = self.modeler.make(seg, mode)
        if asset.is_twoway() and asset.roadtype=='b' and asset.center()[0] == 0:
            preset_lane = 'default' if asset.left.nl() == asset.right.nl() else 'default_asym'
            preset_struc = 'default' if asset.left.nl() == asset.right.nl() else 'default_nostop'
        else:
            preset_lane = preset_struc = 'default_nostop'
        if mode[0] == 's':
            preset_struc = 'none'
        # save lane model
        self.__add_segment('%s_%slanes' % (name, mode), seg_lanes, mode=mode[0], preset=preset_lane, texmode='lane')
        # save structure model, also handles the slope case
        if mode[0] == 's' and type(seg_struc) == tuple:
            struc_up, struc_down = seg_struc
            self.__add_segment('%s_upslope' % name, struc_up, mode=mode[0], preset='slope_up', texmode='tunnel')
            self.__add_segment('%s_downslope' % name, struc_down, mode=mode[0], preset='slope_down', texmode='tunnel')
        elif seg_struc:    
            self.__add_segment('%s_%s' % (name, modename), seg_struc, mode=mode[0], preset=preset_struc, texmode='tunnel' if mode[0] == 's' else None)
        if mode[0] == 't':
            arrows = self.modeler.make_arrows(seg)
            self.__add_segment('%s_arrows' % name, arrows, mode='t', texmode='metro')
        # do not add solid lines in elevated mode
        # note that only road with >1 lanes each side has solid lines
        # the BikeBan flag is used for adding noise barriers
        if mode[0] in 'st' or (mode[0] == 'g' and asset.has_trafficlight()):
            lines = self.modeler.make_solidlines(seg, both=(mode[0] != 'g'))
            if lines:
                filename = ('%s_lines_single' % name) if mode[0] != 'g' else ('%s_lines' % name)
                self.__add_segment(filename, lines, mode=mode[0], preset='bikepolicy', texmode='lane')
        if mode[0] == 'e':
            sb = self.modeler.make_soundbarrier(seg)
            self.__add_segment('%s_soundbarrier' % name, sb, mode=mode[0], preset='bikepolicy', texmode='soundbarrier')
        # add fence to undivided ground road >= 2L
        if mode == 'g' and asset.is_twoway() \
             and asset.is_undivided() and asset.asym() == [0,0] \
             and asset.center() == [0,0] and asset.right.get_all_blocks()[0][0].nlanes > 1:
            self.__add_segment('%s_fence' % name, os.path.join(self.workdir, "models/elem/special/fence"),
                                mode='g', preset="default_nostop", texmode='fence')
        # add side median to weave segments triggered by bikeban
        if mode == 'gw':
            sidemedian = self.modeler.make_sidemedian(seg)
            self.__add_segment('%s_sidemedian' % name, sidemedian, mode=mode[0], preset='bikepolicy', texmode='lane')
    
    def __create_uturn_segment(self, asset):
        mode = 'g'
        modename = self.get_fullname(mode)
        seg = asset.get_model(mode)
        name = self.assetdata['name']
        # make model
        seg_lanes, seg_struc = self.modeler.make_uturn(seg)
        self.__add_segment('%s_%slanes' % (name, mode), seg_lanes, mode=mode[0], preset='default_nostop', texmode='lane')
        self.__add_segment('%s_%s' % (name, modename), seg_struc, mode=mode[0], preset='default_nostop', texmode=None)
        

    def __create_stop(self, asset, mode, busstop):
        if not busstop:
            raise ValueError("stop type should be specified!")
        modename = self.get_fullname(mode)
        seg = asset.get_model(mode)
        name = self.assetdata['name'] + bool(busstop) * '_stop_%s' % busstop
        if busstop == 'brt':
            seg_lanes, seg_struc, brt_f, brt_both = self.modeler.make(seg, mode, busstop=busstop)
            preset = 'default_nostop'
        else:
            seg_lanes, seg_struc = self.modeler.make(seg, mode, busstop=busstop)
            preset = 'stop' + busstop
        self.__add_segment('%s_%slanes' % (name, mode), seg_lanes, mode=mode[0], preset=preset, texmode='lane')
        self.__add_segment('%s_%s' % (name, modename), seg_struc, mode=mode[0], preset=preset)
        if busstop == 'brt':
            self.__add_segment('%s_brt_single' % name, brt_f, mode=mode[0], preset='stopsingle', texmode='brt_platform')
            self.__add_segment('%s_brt_double' % name, brt_both, mode=mode[0], preset='stopdouble', texmode='brt_platform')


    def __create_node(self, asset, mode):
        seg = asset.get_model(mode)
        name = self.assetdata['name'] + '_' + mode + '_node'
        if mode in ['g', 'gc']:
            tex_side = 'node'
        elif mode == 'ge':
            tex_side = 'lane'
        sidewalk, sidewalk2, asphalt, junction = self.modeler.make_node(seg, mode[0])
        sidewalk_comp, asphalt_comp = self.modeler.make_node(seg, mode[0], compatibility=True)
        if sidewalk2:
            self.__add_node('%s_sidewalk_crossing' % name, sidewalk, preset='trafficlight_nt', texmode=tex_side)
            self.__add_node('%s_sidewalk_nocrossing' % name, sidewalk2, preset='notrafficlight_nt', texmode=tex_side)
        else:
            self.__add_node('%s_sidewalk_crossing' % name, sidewalk, preset='default', texmode='node')
        # asphalt and junction always use node texture
        self.__add_node('%s_asphalt' % name, asphalt, preset='default', texmode='node')
        if junction:
            self.__add_node('%s_junction' % name, junction, preset='trafficlight', texmode='node')
        self.__add_node('%s_sidewalk_comp' % name, sidewalk_comp, preset='transition', texmode=tex_side)
        self.__add_node('%s_asphalt_comp' % name, asphalt_comp, preset='transition', texmode='node')
    

    def __create_dcnode(self, asset, mode, target_median=None, asym_mode=None):
        MW = 1.875
        seg = asset.get_model(mode)
        if target_median is None:
            medians = None
            target_median = self.__get_mediancode(asset)
        else:
            split = 1 if target_median[0] != '-' else 2
            medians = [-int(target_median[:split])*MW, int(target_median[split:])*MW]
        if asym_mode != 'invert':
            if asym_mode == 'restore':
                dcnode, target_median = self.modeler.make_asym_restore_node(seg)
                print(target_median)
                name = '%s_restorenode' % self.assetdata['name']
            elif asym_mode == 'expand':
                dcnode, target_median = self.modeler.make_asym_invert_node(seg, halved=True) 
                print(target_median)
                name = '%s_expandnode' % self.assetdata['name']
            else:
                dcnode = self.modeler.make_dc_node(seg, target_median=medians)
                name = '%s_dcnode_%s' % (self.assetdata['name'], target_median)
            connectgroup = self.get_connectgroup(target_median)
            self.__add_node(name, dcnode, preset='direct', connectgroup=connectgroup, texmode='lane')
        else:
            # note that "bend node" is actually a segment in the game
            asym_forward, asym_backward = self.modeler.make_asym_invert_node(seg, halved=False)
            self.__add_segment('%s_asymforward' % self.assetdata['name'], asym_forward, mode='g', preset='asymforward', texmode='lane')
            self.__add_segment('%s_asymbackward' % self.assetdata['name'], asym_backward, mode='g', preset='asymbackward', texmode='lane')

    def __create_local_express_dcnode(self, asset, target_median=None):
        MW = 1.875
        seg = asset.get_model('g')
        dlanes = (target_median - int(asset.right.get_all_blocks()[0][0].x_right / SW.MEDIAN)) // 2
        dcnode = self.modeler.make_local_express_dc_node(seg, dlanes)
        le_connectgroup = self.connectgroup_side[target_median]
        name = '%s_dcnode_le%s' % (self.assetdata['name'], target_median)
        self.__add_node(name, dcnode, preset='direct', connectgroup=le_connectgroup, texmode='lane')
        
    def __create_brtnode(self, asset):
        if not asset.is_twoway():
            raise ValueError("BRT station should be created on two-way roads!")
        mode = 'g'
        seg = asset.get_model(mode)
        blocks = asset.right.get_all_blocks()[0]
        seg_l = csur.CSURFactory(mode=mode, roadtype='b').get(
                                    blocks[0].x_left, blocks[0].nlanes)
        seg_r = csur.CSURFactory(mode=mode, roadtype='s').get([
                                    blocks[1].x_left - SW.MEDIAN, blocks[1].x_left], blocks[1].nlanes)
        dc_seg = csur.CSURFactory.fill_median(seg_l, seg_r, 's')
        dc_seg = csur.TwoWay(dc_seg.reverse(), dc_seg)
        model = self.modeler.convert_to_dcnode(dc_seg, keep_bikelane=False)
        self.__add_node('%s_brtnode' % self.assetdata['name'], model, 
                        preset='direct', 
                        connectgroup=self.get_connectgroup(self.__get_mediancode(asset)), 
                        texmode='lane')
        

    # TODO: change speed limits
    def __create_lanes(self, asset, mode, seg=None, reverse=False, brt=False):
        modename = self.get_basename(mode)
        if asset.is_twoway() and not seg:
            seg = asset.get_model(mode)
            self.__create_lanes(asset, mode, seg=seg.left, reverse=True, brt=brt)
            if not asset.is_undivided() and asset.append_median:
                median_lane = deepcopy(self.lanes['median'])
                # add traffic lights and road lights to median, lane position is always 0 to let NS2 work
                median_pos = (min(seg.right.x_start[0], seg.right.x_end[0]))
                if mode[0] in "ge":
                    prop_utils.add_props(median_lane, median_pos, self.props["light_median"])
                if mode[0] == "t" and asset.roadtype == 'b':
                    light_r = seg.right.x_start[seg.right.start.index(Segment.LANE)] - SW.BARRIER
                    light_l = -seg.left.x_start[seg.left.start.index(Segment.LANE)] + SW.BARRIER
                    # light at right side of the median is flipped (equiv. left barrier)
                    prop_utils.add_props(median_lane, light_r, prop_utils.flip(deepcopy(self.props["light_tunnel"])))
                    prop_utils.add_props(median_lane, light_l, self.props["light_tunnel"])
                if asset.has_trafficlight():
                    # wide median is used if the road is wider than 6L
                    if max(asset.get_dim()) > 6 * SW.LANE:
                        prop_set = self.props["intersection_widemedian"]
                        xl = -asset.left.xleft[0] + SW.CURB
                        xr = asset.right.xleft[0] - SW.CURB
                    else:
                        prop_set = self.props["intersection_median"]
                        xl = xr = median_pos
                    prop_utils.add_intersection_props(median_lane, xr, prop_set)
                    prop_utils.add_intersection_props(median_lane, xl, prop_utils.flip(prop_set))
                self.assetdata[modename]['m_lanes']['Lane'].append(median_lane)
            self.__create_lanes(asset, mode, seg=seg.right, reverse=False, brt=brt)
        else:
            # keeps a bus stop lane cache; if the segment is a BRT module
            # then caches the first lane, else caches the last lane
            if not seg:
                seg = asset.get_model(mode)
            shift_lane_flag = False
            di_start = di_end = 0
            busstop_lane = None
            brt_sidewalk = False
            for i, zipped in enumerate(zip(seg.start, seg.end)):
                u_start, u_end = zipped
                lane = None
                if u_start == u_end:
                    if not shift_lane_flag and seg.roadtype() == 's' and min(seg.n_lanes()) > 1 and u_start == Segment.LANE:
                        if seg.x_start[0] - seg.x_end[0] > SW.LANE / 2:
                            di_start = -1
                            shift_lane_flag = True
                            continue
                        elif seg.x_end[0] - seg.x_start[0] > SW.LANE / 2:
                            di_end = -1
                            shift_lane_flag = True
                            continue
                    if u_start != Segment.LANE:
                        di_start = di_end = 0
                        shift_lane_flag = False
                    pos_start = (seg.x_start[i + di_start] + seg.x_start[i + 1 + di_start]) / 2
                    pos_end = (seg.x_end[i + di_end] + seg.x_end[i + 1 + di_end]) / 2
                    pos = (pos_start + pos_end) / 2
                    if u_start == Segment.LANE:
                        lane = deepcopy(self.lanes['car'])
                        if not (busstop_lane and brt):
                            busstop_lane = lane
                        # change prop positions in the car lane
                        for p in lane["m_laneProps"]["Prop"]:
                            deltax = (pos_end - pos_start) * float(p["m_segmentOffset"]) / 2
                            p["m_position"]["float"][0] = str(float(p["m_position"]["float"][0]) + deltax)
                    elif u_start == Segment.MEDIAN and brt and not brt_sidewalk and i > 0:
                        lane = deepcopy(self.lanes['ped'])
                        pos += SW.MEDIAN / 2
                        brt_sidewalk = True
                    elif u_start == Segment.BIKE:
                        lane = deepcopy(self.lanes['bike'])
                        # change bike lane direction to BOTH if the road has two BIKE units
                        if sum([u == Segment.BIKE for u in u_start]) > 1:
                            lane["m_direction"] = "Both"
                            lane["m_finalDirection"] = "Both"
                    elif u_start == Segment.SIDEWALK:
                        lane = deepcopy(self.lanes['ped'])
                        if brt:
                            lane["m_stopType"] = "None"
                        # add ped lane props, first we determine where the car lanes end
                        # should distinguish between left and right sidewalks
                        if i == 0:
                            i_side = len(csur.CSURFactory.roadside[mode]) - 1
                            x_side = (seg.x_start[i_side + 1] + seg.x_end[i_side + 1]) / 2
                            k = -1
                        else:
                            i_side = len(seg.start) - len(csur.CSURFactory.roadside[mode])
                            k = 1
                            x_side = (seg.x_start[i_side] + seg.x_end[i_side]) / 2
                        # determine the location where props are placed
                        if seg.start[i_side] == Segment.MEDIAN:
                            prop_pos = x_side + k * (SW.MEDIAN / 2) - pos
                            height = 0.05
                        elif seg.start[i_side] == Segment.CURB:
                            prop_pos = x_side + k * SW.CURB - pos
                            height = 0.15
                        elif seg.start[i_side] == Segment.PARKING:
                            prop_pos = x_side + k * (SW.CURB + SW.PARKING) - pos
                            height = 0.15
                        else:
                            raise NotImplementedError
                        prop_pos *= k

                        # add lights and trees
                        if seg.x_start[i_side] == seg.x_end[i_side]:
                            prop_utils.add_props(lane, prop_pos, self.props["light_side"], height=height)
                            prop_utils.add_props(lane, prop_pos, self.props["random_street_prop"], height=height)
                            prop_utils.add_props(lane, prop_pos, self.props["tree_side"], height=height)
                        else:
                            light = deepcopy(self.props["light_side"])
                            for p in light:
                                p["m_repeatDistance"] = "0"
                            prop_utils.add_props(lane, prop_pos, light, height=height)
                            # two trees at -0.33 and + 0.33
                            tree_zpos = [-0.33, 0.33]
                            for z in tree_zpos:
                                tree = deepcopy(self.props["tree_side"])
                                for t in tree:
                                    t["m_repeatDistance"] = "0"
                                    t["m_segmentOffset"] = str(z)
                                deltax = (seg.x_end[i_side] - seg.x_start[i_side]) * z
                                prop_utils.add_props(lane, prop_pos + deltax, tree, height=height)
                        # add intersection props
                        if asset.has_trafficlight():
                            prop_utils.add_intersection_props(lane, prop_pos, self.props["intersection_side"], height=0)
                            # railway crossings should always be placed on sidewalks
                            if seg.start[i_side] == Segment.MEDIAN:
                                prop_pos += SW.MEDIAN / 2 + SW.BIKE + SW.CURB
                            prop_utils.add_intersection_props(lane, prop_pos, self.props["railway_crossing"], height=0)
                        # add bus stop props
                        if asset.has_busstop():
                            prop_pos = (seg.x_start[-1] + seg.x_start[-2]) / 2 - pos
                            if Segment.BIKE not in u_start:
                                prop_pos += 5
                            prop_utils.add_props(lane, prop_pos, self.props["busstop"])

                    elif mode[0] in "et" and u_start == Segment.BARRIER:
                        # only use left barrier light if width >= 5L
                        if i > 0 or (max(seg.width()) > 5 * SW.LANE and mode[0] == 'e') or (max(seg.width()) > 2 * SW.LANE and mode[0] == 't'):
                            pos_start = seg.x_start[-1 * (i != 0)]
                            pos_end = seg.x_end[-1 * (i != 0)]
                            pos = (pos_start + pos_end) / 2
                            lane = deepcopy(self.lanes['barrier'])
                            light = deepcopy(self.props["light_tunnel" if mode[0] == 't' else "light_side"])
                            if i == 0:
                                light = prop_utils.flip(light)
                            if seg.x_start[-1 * (i != 0)] != seg.x_end[-1 * (i != 0)]:
                                for p in light:
                                    p["m_repeatDistance"] = "0"
                            prop_utils.add_props(lane, 0, light)
                    if lane is not None:
                        # non-median lanes should never have 0 position,
                        # otherwise it confuses NS2
                        if pos == 0:
                            pos = 0.05
                        lane["m_position"] = str(-pos if reverse else pos)
                        if reverse or (u_start == Segment.SIDEWALK and i == 0):
                            lane = prop_utils.flip_lane(lane)                                  
                        self.assetdata[modename]['m_lanes']['Lane'].append(lane)
            # applies stop offset
            if mode[0] == 'g':
                if not brt:
                    busstop_lane["m_stopOffset"] = "-3" if reverse else "3"
                else:
                    busstop_lane["m_stopOffset"] = "-0.3" if reverse else "0.3"

    def __get_mediancode(self, asset):
        if not asset.is_twoway():
            return 'None'
        medians = asset.n_central_median()
        return str(medians[0]) + str(medians[1])

    def __write_netAI(self, asset, mode):
        seg = asset.get_model(mode)
        modename = self.get_basename(mode)
        if mode[0] == 'g' and asset.is_twoway() and asset.roadtype == 'b':
            self.assetdata['%sAI' % modename]['m_trafficLights'] = 'true' 
        else:
            self.assetdata['%sAI' % modename]['m_trafficLights'] = 'false'
      
        # construction cost
        BASE_CONSTRUCT_COST = 2000
        BASE_MAINTAIN_COST = 150
        nl = asset.nl_min()
        nmedian = min(asset.get_dim()) / SW.LANE - nl
        if mode[0] == 'g':
            if mode[0] == 'ge':
                coeff = nl + nmedian * 0.5  
            elif mode[0] == 'gc':
                coeff = nl + nmedian * 0.5 + 0.5
            else:
                coeff = nl + nmedian * 0.5 + 1
        elif mode[0] in 'be':
            coeff = 2 * nl
        else:
            coeff = 4 * nl
        self.assetdata['%sAI' % modename]["m_constructionCost"] = str(coeff * BASE_CONSTRUCT_COST)
        self.assetdata['%sAI' % modename]["m_maintenanceCost"] = str(coeff * BASE_MAINTAIN_COST)
                 


    def __write_info(self, asset, mode):
        seg = asset.get_model(mode)
        modename = self.get_basename(mode)
        info = self.assetdata[modename]
        if type(seg) == csur.TwoWay:
            if asset.roadtype == 'b':
                info["m_connectGroup"] = self.get_connectgroup(self.__get_mediancode(asset))
                if len(asset.right.get_all_blocks()[0]) == 2:
                    my_sidemedian = int(asset.right.get_all_blocks()[0][0].x_right / SW.MEDIAN)
                    info["m_connectGroup"] += ' ' + self.connectgroup_side[my_sidemedian]
            else:
                info["m_connectGroup"] = "None"
            halfwidth = min([max(seg.right.x_start), max(seg.left.x_start)])
            if mode[0] == 'g':
                if seg.right.start[-1] == Segment.SIDEWALK:
                    halfwidth -= 1.25
                elif seg.right.start[-1] == Segment.CURB:
                    halfwidth = min([seg.right.x_start[-1], seg.left.x_start[-1]]) + 2.5
                else:
                    raise NotImplementedError("Unknown ground mode variant, cannot calculate half width!")
            else:
                halfwidth += 1.25
            if asset.roadtype == 'b':
                # asymmetric segments
                if asset.asym()[0] > 0:
                    halfwidth += asset.asym()[0] * 1e-5
                else:
                    # local-express segment (always symmetric)
                    blocks = asset.right.get_all_blocks()[0]
                    if len(blocks) == 2:
                        # magic number controlling hetrogeneous DC nodes
                        halfwidth += (blocks[0].nlanes - blocks[1].nlanes) * 8e-5
                    # wide median segments
                    if asset.n_central_median()[0] > 1:
                        halfwidth += (asset.n_central_median()[0] - 1) * 1e-6
            # change min corner offset, increase the size of intersections
            # for roads wider than 6L
            # only apply to base modules
            if mode[0] == 'g' and asset.roadtype == 'b':
                #if min(asset.get_dim()) > 6 * SW.LANE:
                #    scale = 1 + (min(asset.get_dim()) - 3 * SW.LANE) / (SW.LANE * 20)
                #else:
                #    scale = 0.8
                if min(asset.get_dim()) > 6 * SW.LANE:
                    scale = 1 + (min(asset.get_dim()) - 3 * SW.LANE) / (SW.LANE * 25)
                else:
                    scale = 1
                info["m_minCornerOffset"] = str(halfwidth * scale)
                # clips terrain when there is median
                if asset.append_median and mode != 'ge':
                    info["m_clipTerrain"] = "true"
                    info["m_flattenTerrain"] = "true"
                    info["m_createPavement"] = "true"
                else:
                    info["m_clipTerrain"] = "false"
                    info["m_flattenTerrain"] = "false"
                    info["m_createPavement"] = "false"
            # for any ground nodeless road corner offset and clip segment the same as one-way modules
            if seg.roadtype() != 'b':
                info["m_createPavement"] = "false"
                info["m_pavementWidth"] = "-3"
                info["m_enableBendingNodes"] = "false"
                info["m_clipSegmentEnds"] = "false"
                info["m_minCornerOffset"] = "0"
        else:
            info["m_connectGroup"] = "None"
            # for roads with offset the halfwidth is the absolute max x value, pavementwidth is the absolute min x value
            if seg.roadtype() != 'b' or seg.x_start[0] + seg.x_start[-1] != 0:
                halfwidth = max(seg.x_start + seg.x_end)
                info["m_pavementWidth"] = str(min(seg.x_start + seg.x_end))
                info["m_createPavement"] = "false"
                info["m_clipTerrain"] = "false"
                info["m_enableBendingNodes"] = "false"
                info["m_clipSegmentEnds"] = "false"
                info["m_minCornerOffset"] = "0"
            else:
                halfwidth = max(seg.x_start)
                if seg.start[-1] == Segment.SIDEWALK:
                    halfwidth -= 1.25
                if mode[0] != 'g':
                    halfwidth += 1.25
            # slope mode must flatten terrain
            if mode[0] == 's':
                info["m_flattenTerrain"] = "true"
            else:
                info["m_flattenTerrain"] = "false"         
        info["m_halfWidth"] = "%.8f" % halfwidth
        if asset.roadtype == 'b':
            info["m_enableBendingSegments"] = "true"
        # write UI Category, only on basicInfo
        if mode[0] == 'g':
            if asset.roadtype == 'b' and asset.center()[0] == 0:
                category = "CSUR_Roads_MAIN"
            else:
                category = "CSUR_Roads_%s" % csur.typename[asset.roadtype]   
            info["m_UICategory"] = category
        # special: change segmentlength to 60 for shift segments 
        if not asset.is_twoway() and asset.roadtype == 's':
            info["m_segmentLength"] = ["60"]

        # speed limit
        # TODO: apply speed limit to each car lane
        if mode[0] == 'g':
            if mode == 'ge':
                speed = 160
            else:
                speed = max(10 * (2 + asset.nl_min()), 60)
        if mode[0] in 'be':
            speed = min(60, max(0.2 * (2 + 2 * asset.nl_min()), 100))
        if mode[0] in 'st':
            speed = min(40, max(0.2 * (2 + 2 * asset.nl_min()), 80))
        for lane in self.assetdata[modename]['m_lanes']['Lane']:
            if lane["m_laneType"] == "Vehicle" and lane["m_vehicleType"] == "Car":
                lane["m_speedLimit"] = str(speed / 50)


    def __get_light(self, asset, position, mode):
        # median lights
        if position == "median":
            if mode == "g":
                if min(asset.get_dim()) > 4 * SW.LANE:
                    return self.skins['light']['median_gnd']
            elif mode == "e":
                if min(asset.get_dim()) > 10 * SW.LANE:
                    return self.skins['light']['median_elv']
        # side lights
        elif position == "side":
            if mode == "g":
                if asset.is_twoway() and asset.is_undivided():
                    return self.skins['light']['side_gnd_large']
                elif min(asset.get_dim()) > 10 * SW.LANE:
                    return self.skins['light']['side_gnd_large']
                # divided roads narrower than 5L does not need side light
                elif asset.is_twoway() and min(asset.get_dim()) < 6 * SW.LANE:
                    return None
                else:
                    return self.skins['light']['side_gnd_small']
            elif mode == "e":
                return self.skins['light']['side_elv']
            elif mode == "t":
                return self.skins['light']['side_tun']
        return None

    '''
    Positions of lights and trees are included in the lane
    templates. The method searches for them using an identifier
    in the prop/tree name 'CSUR@*:*' then replaces them with the
    asset name in the skins file. If the prop/tree should not exist,
    it will be removed from the lane.
    '''
    def __apply_skin(self, asset, mode):
        modename = self.get_basename(mode)
        for i, lane in enumerate(self.assetdata[modename]['m_lanes']['Lane']):
            # lights or trees should always be placed on a line with direction BOTH
            # TODO: remove barrier lanes and move lights into car lanes,
            # this requires to check also the first and last lane
            if i == 0 or i == len(self.assetdata[modename]['m_lanes']['Lane']) - 1 or lane["m_direction"] == "Both":
                removed = []
                for i, prop in enumerate(lane["m_laneProps"]["Prop"]):
                    if prop["m_prop"] and prop["m_prop"][:5] == "CSUR@":
                        split = prop["m_prop"][5:].lower().split(':')
                        if split[0] == "light":
                            # remove left side light for roads < 4DC
                            if min(asset.get_dim()) < 4 * SW.LANE and float(lane["m_position"]) < -SW.LANE:
                                key = None
                            else:
                                key = self.__get_light(asset, split[1], mode[0])             
                        elif split[0] == 'sign':
                            proplist = self.skins[split[0].lower()][split[1].lower()]
                            if not asset.is_twoway():
                                key = None
                            else:
                                nlane = asset.left.nl() if float(prop["m_angle"]) < 0 else asset.right.nl()
                                key = proplist[min(len(proplist), nlane) - 1]
                        else:
                            raise ValueError("Invalid CSUR@ skin type: %s" % split)
                        if not key:
                            removed.append(i)
                        else:
                            prop["m_prop"] = key
                    if prop["m_tree"] and prop["m_tree"][:9] == "CSUR@TREE":
                        split = prop["m_tree"][5:].lower().split(':')
                        tree = self.skins[split[0]][split[1]]
                        if not tree:
                            removed.append(i)
                        else:
                            prop["m_tree"] = tree
                for i in removed[::-1]:
                    lane["m_laneProps"]["Prop"].pop(i)
        # place pillars, only base module has pillars
        if mode[0] == 'e' and asset.roadtype == 'b':
            if asset.is_twoway() and not asset.is_undivided():
                pillar = self.skins['pillar']['twoway'][int(min(asset.get_dim()) / SW.LANE / 2) - 1]
            else:
                blocks = asset.get_all_blocks()[0]
                if blocks[0].x_left * blocks[-1].x_right < 0:
                    pillar = self.skins['pillar']['twoway'][int(min(asset.get_dim()) / SW.LANE / 2) - 1]
                else:
                    pillar = None
            self.assetdata['elevatedAI']['m_bridgePillarInfo'] = pillar[0]
            self.assetdata['elevatedAI']['m_bridgePillarOffset'] = str(pillar[1])

    def writetoxml(self, asset):
        path = os.path.join(self.output_path, self.assetdata['name'] + '_data.xml')
        xmlserializer.write(self.assetdata, 'RoadAssetInfo', path)
        self.modeler.cleanup()
        self.assets_made.append(self.assetdata['name'])

    def write_thumbnail(self, asset):
        path = os.path.join(self.output_path, self.assetdata['name'])
        draw(asset, os.path.join(self.workdir, 'img/color.ini'), path)
        for mode in ['disabled', 'hovered', 'focused', 'pressed']:
            draw(asset, os.path.join(self.workdir, 'img/color.ini'), path, mode=mode)

    def __create_all_nodes(self, asset, mode):
        self.__create_node(asset, mode)
        if asset.is_twoway():
            n_central_median = asset.n_central_median()
            if n_central_median[0] == n_central_median[1]:
                # only create DC node for >3 lanes
                if asset.nl() > 3:
                    self.__create_dcnode(asset, mode)
                    if n_central_median[0] == 1:
                        self.__create_dcnode(asset, mode, target_median='33')
                    if n_central_median[0] == 0:
                        self.__create_dcnode(asset, mode, target_median='11')
                    if len(asset.right.get_all_blocks()[0]) == 2:
                        my_sidemedian = int(asset.right.get_all_blocks()[0][0].x_right / SW.MEDIAN)
                        self.__create_local_express_dcnode(asset, my_sidemedian)
                        for target_median in self.connectgroup_side.keys():
                            # sidemedian=2 used for BRT station
                            # same rule as normal DC node, from side to center
                            if 2 < target_median < my_sidemedian:
                                self.__create_local_express_dcnode(asset, target_median)
            else:
                if asset.nl() > 3:
                    if not asset.is_undivided():
                        self.__create_dcnode(asset, mode)
                        self.__create_dcnode(asset, mode, asym_mode='expand')
                        # Asym roads whose center is not convered by median
                        # this implies the number of lanes are at least different by 2 
                        # between both sides
                        if n_central_median[0] > n_central_median[1] and n_central_median[0] + n_central_median[1] > 2:
                            self.__create_dcnode(asset, mode, target_median=str(n_central_median[0]) + str(-n_central_median[1]))
                    self.__create_dcnode(asset, mode, asym_mode='invert')   
                    self.__create_dcnode(asset, mode, asym_mode='restore')
    
    def make(self, asset, weave=False):
        self.__initialize_assetinfo(asset)
        modes = ['g', 'e']
        if self.tunnel:
            modes.append('t')
        if weave:
            modes = [x + 'w' for x in modes]
        if asset.roadtype == 'b':
            if self.bridge:
                modes.append('b')
            if self.tunnel:
                modes.append('s')
        # build segments
        for mode in modes:
            self.__create_segment(asset, mode)
        # build node. centered roads only
        if asset.roadtype == 'b' and asset.center()[0] == 0:
            # first mode is ground
            self.__create_all_nodes(asset, modes[0])
            # only allow bus stops on ground normal
            if modes[0] in ['g', 'gc']: 
                self.__create_stop(asset, modes[0], 'single')
                if asset.is_twoway():
                    self.__create_stop(asset, modes[0], 'double') 
        # write data
        for mode in modes:
            self.__create_lanes(asset, mode)
            self.__write_netAI(asset, mode)
            self.__write_info(asset, mode)
            if mode[0] in 'get':
                self.__apply_skin(asset, mode)
        self.writetoxml(asset)
        self.write_thumbnail(asset)
        return self.assetdata

    def make_singlemode(self, asset, mode, node=True):
        self.__initialize_assetinfo(asset)
        self.assetdata['name'] = str(asset.get_model(mode[0]))
        if len(mode) > 1:
            self.assetdata['name'] += ' ' + AssetMaker.suffix[mode[1]] 
        self.__create_segment(asset, mode)
        if node and asset.roadtype == 'b' and asset.center()[0] == 0:
            self.__create_all_nodes(asset, mode)
        if mode in ['g', 'gc']: 
            self.__create_stop(asset, mode, 'single')
            if asset.is_twoway():
                self.__create_stop(asset, mode, 'double') 
        self.__create_lanes(asset, mode)
        self.__write_netAI(asset, mode)
        self.__write_info(asset, mode)
        if mode[0] in 'get':
            self.__apply_skin(asset, mode)
        self.writetoxml(asset)
        self.write_thumbnail(asset)
        return self.assetdata

    def make_uturn(self, asset):
        self.__initialize_assetinfo(asset)
        self.assetdata['name'] += ' uturn'
        self.__create_uturn_segment(asset)
        # use a delegate twoway asset to create node
        al = assets.Asset(asset.left.xleft[1], asset.left.nlanes[1])
        ar = assets.Asset(asset.right.xleft[1], asset.right.nlanes[1])
        delegate = assets.TwoWayAsset(al, ar)
        self.__create_node(delegate, 'g')
        self.__create_lanes(delegate, 'g')
        self.__write_netAI(asset, 'g')
        self.__write_info(asset, 'g')
        self.__apply_skin(asset, 'g')
        self.writetoxml(asset)
        self.write_thumbnail(asset)
        return self.assetdata


    def make_brt(self, asset):
        self.__initialize_assetinfo(asset)
        self.__create_stop(asset, 'g', 'brt')
        self.__create_node(asset, 'g')
        self.__create_brtnode(asset)
        self.__create_lanes(asset, 'g', brt=True)
        self.__write_netAI(asset, 'g')
        self.__write_info(asset, 'g')
        self.assetdata['basic']["m_connectGroup"] = "None"
        self.__apply_skin(asset, 'g')
        self.writetoxml(asset)
        self.write_thumbnail(asset)
        return self.assetdata

    def output_assets(self):
        with open(os.path.join(self.output_path, 'imports.txt'), 'w+') as f:
            f.writelines(["%s\n" % x for x in self.assets_made])