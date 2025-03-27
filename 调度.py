'''版本3：gurobi，高峰小时实际数据。局限：未考虑实际路网
'''
import random
import math
import pandas as pd
import gurobipy as gp
from gurobipy import GRB

# 固定车辆行驶速度（每周期行驶距离，单位：km）
# 40 km/h 对应 5 分钟行驶距离
TRAVEL_SPEED = 40 / 12  

def haversine_distance(coord1, coord2):
    """
    计算两个经纬度点之间的球面距离（单位：km）
    coord 格式：(lat, lon)，角度单位：度
    """
    R = 6371  # 地球半径（km）
    lat1, lon1 = map(math.radians, coord1)
    lat2, lon2 = map(math.radians, coord2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

class Vehicle:
    def __init__(self, vid, position, battery):
        self.vid = vid
        self.position = position  # (lat, lon)
        self.battery = battery
        self.status = 'idle'
        self.current_order = None
        self.charging_station = None
        # 充电相关属性
        self.charge_target = None
        self.charge_start_position = None
        self.charge_travel_time = None
        self.charge_travel_remaining = None
        # 载客前往接乘客相关属性
        self.trip_start_position = None
        self.trip_travel_time = None
        self.trip_travel_remaining = None

class Order:
    def __init__(self, oid, pickup, destination, length, stime, cycle):
        self.oid = oid            # 使用 Excel 中的订单编号
        self.pickup = pickup      # (lat, lon)
        self.destination = destination  # (lat, lon)
        self.length = length      # km
        self.status = 'unassigned'
        # 根据车辆每周期行驶距离，计算订单所需周期（至少 1 个周期）
        self.duration = max(1, math.ceil(length / TRAVEL_SPEED))
        self.remaining = self.duration
        self.start_position = None  # 记录开始载客后车辆的位置（从 pickup 出发）
        self.stime = stime        # 请求开始时间（秒）
        self.cycle = cycle        # 订单所属周期（0~11）

class ChargingStation:
    def __init__(self, cid, position):
        self.cid = cid
        self.position = position  # (lat, lon)
        self.charging_vehicles = []

class Scheduler:
    def __init__(self):
        self.vehicles = []
        self.orders = []         # 当前待调度订单池
        self.all_orders = []     # 所有订单（加载后按周期分组）
        self.orders_by_cycle = {}# key: cycle (0~11)，value: list of Order 对象
        self.stations = []
        self.current_cycle = 0
        self.total_profit = 0

    def load_order_data(self, excel_path):
        """
        读取 Excel 数据：
          - 筛选 SHour 为 9 的订单（9 点高峰）
          - 订单起点列：SLon, SLat，终点列：ELon, ELat
          - 出行距离 TD 单位为 m，转换为 km
          - 计算订单所属周期：周期 = int((STime % 3600) // 300)
          - 使用 Excel 中的订单编号 "index_right" 作为订单 id
        注意：为了与 haversine 计算匹配，pickup 和 destination 坐标格式采用 (lat, lon)
        """
        df = pd.read_excel(excel_path)
        df_peak = df[df['SHour'] == 9].copy()
        df_peak['cycle'] = df_peak['STime'].apply(lambda t: int((t % 3600) // 300))
        df_peak['length_km'] = df_peak['TD'] / 1000.0
        orders = []
        for idx, row in df_peak.iterrows():
            pickup = (row['SLat'], row['SLon'])
            destination = (row['ELat'], row['ELon'])
            order = Order(
                oid = row['index_right'],  # 使用 Excel 中的订单编号
                pickup = pickup,
                destination = destination,
                length = row['length_km'],
                stime = row['STime'],
                cycle = row['cycle']
            )
            orders.append(order)
        self.all_orders = orders
        self.orders_by_cycle = {i: [] for i in range(12)}
        for order in orders:
            if 0 <= order.cycle < 12:
                self.orders_by_cycle[order.cycle].append(order)

    def initialize(self, n_vehicles=500, n_stations=100, excel_path=r"C:\D学习\小论文\数据\成都一天.xlsx"):
        # 加载订单数据
        self.load_order_data(excel_path)
        # 根据订单数据计算经纬度范围（采用订单起点和终点）
        all_lats = []
        all_lons = []
        for order in self.all_orders:
            all_lats.extend([order.pickup[0], order.destination[0]])
            all_lons.extend([order.pickup[1], order.destination[1]])
        min_lat, max_lat = min(all_lats), max(all_lats)
        min_lon, max_lon = min(all_lons), max(all_lons)
        
        # 初始化车辆，均匀分布在订单经纬度范围内（格式：(lat, lon)）
        for i in range(n_vehicles):
            lat = random.uniform(min_lat, max_lat)
            lon = random.uniform(min_lon, max_lon)
            battery = random.uniform(50, 100)
            self.vehicles.append(Vehicle(i, (lat, lon), battery))
        
        # 初始化充电站（随机生成 n_stations 个，位置在相同范围内）
        for i in range(n_stations):
            lat = random.uniform(min_lat, max_lat)
            lon = random.uniform(min_lon, max_lon)
            self.stations.append(ChargingStation(i, (lat, lon)))
    
    def add_new_orders(self, cycle):
        """将当前周期内的订单添加到待调度池"""
        if cycle in self.orders_by_cycle:
            self.orders.extend(self.orders_by_cycle[cycle])
    
    def update_states(self):
        # 运动中车辆电量衰减，每周期减少 5
        for v in self.vehicles:
            if v.status in ['to-charge', 'to-trip', 'on-trip']:
                v.battery = max(v.battery - 5, 0)
                
        # 0. 更新前往充电站车辆的位置（状态为 "to-charge"）
        for v in self.vehicles:
            if v.status == 'to-charge' and v.charge_target is not None:
                if v.charge_start_position is None:
                    v.charge_start_position = v.position
                v.charge_travel_remaining -= 1
                fraction = (v.charge_travel_time - v.charge_travel_remaining) / v.charge_travel_time
                fraction = min(1, fraction)
                start_lat, start_lon = v.charge_start_position
                target_lat, target_lon = v.charge_target.position
                new_lat = start_lat + (target_lat - start_lat) * fraction
                new_lon = start_lon + (target_lon - start_lon) * fraction
                v.position = (new_lat, new_lon)
                if v.charge_travel_remaining <= 0:
                    v.position = v.charge_target.position
                    v.charging_station = v.charge_target
                    v.status = 'charging(available)' if v.battery >= 30 else 'charging(unavailable)'
                    v.charge_target.charging_vehicles.append(v)
                    v.charge_target = None
                    v.charge_start_position = None
                    v.charge_travel_time = None
                    v.charge_travel_remaining = None

        # 1. 更新前往接乘客阶段车辆的位置（状态为 "to-trip"）
        for v in self.vehicles:
            if v.status == 'to-trip' and v.current_order is not None:
                if v.trip_start_position is None:
                    v.trip_start_position = v.position
                v.trip_travel_remaining -= 1
                fraction = (v.trip_travel_time - v.trip_travel_remaining) / v.trip_travel_time
                fraction = min(1, fraction)
                start_lat, start_lon = v.trip_start_position
                target_lat, target_lon = v.current_order.pickup
                new_lat = start_lat + (target_lat - start_lat) * fraction
                new_lon = start_lon + (target_lon - start_lon) * fraction
                v.position = (new_lat, new_lon)
                if v.trip_travel_remaining <= 0:
                    v.position = v.current_order.pickup
                    v.current_order.start_position = v.position
                    v.status = 'on-trip'
                    v.trip_start_position = None
                    v.trip_travel_time = None
                    v.trip_travel_remaining = None

        # 2. 更新已上车车辆的位置，从 pickup 到 destination
        for v in self.vehicles:
            if v.status == 'on-trip' and v.current_order is not None:
                order = v.current_order
                if order.start_position is None:
                    order.start_position = v.position
                fraction = min(1, (order.duration - order.remaining + 1) / order.duration)
                start_lat, start_lon = order.start_position
                dest_lat, dest_lon = order.destination
                new_lat = start_lat + (dest_lat - start_lat) * fraction
                new_lon = start_lon + (dest_lon - start_lon) * fraction
                v.position = (new_lat, new_lon)
        
        # 3. 更新充电中的车辆电量状态（仅限停在充电站的车辆）
        for v in self.vehicles:
            if v.status == 'charging(available)':
                v.battery = min(100, v.battery + 20)  # 快充，每周期充20%
            elif v.status == 'charging(unavailable)':
                v.battery = min(100, v.battery + 20)  # 慢充，每周期充10%
            # 如果车辆充电过程中，电量已满则更新状态为 idle
            if v.status.startswith('charging'):
                if v.battery >= 80:
                    v.status = 'idle'
                    if v.charging_station is not None and v in v.charging_station.charging_vehicles:
                        v.charging_station.charging_vehicles.remove(v)
                    v.charging_station = None
                else:
                    v.status = 'charging(available)' if v.battery >= 30 else 'charging(unavailable)'
        
        # 4. 更新在途车辆订单剩余时间，完成后更新状态和位置
        for v in self.vehicles:
            if v.status == 'on-trip' and v.current_order is not None:
                v.current_order.remaining -= 1
                if v.current_order.remaining <= 0:
                    v.position = v.current_order.destination
                    v.status = 'idle'
                    v.current_order = None
                    
        # 5. 同步更新订单状态
        for o in self.orders:
            if o.status == 'assigned' and o.remaining <= 0:
                o.status = 'completed'
    
    def get_available_vehicles(self):
        available = []
        for v in self.vehicles:
            if v.status in ['idle', 'charging(available)']:
                available.append(v)
            elif v.status == 'to-charge' and v.battery >= 30:
                available.append(v)
        return available
    
    def get_available_orders(self):
        return [o for o in self.orders if o.status == 'unassigned']
    
    def schedule(self):
        """
        使用 Gurobi 模型进行车辆与订单/充电站匹配。
        订单匹配收益 = 订单长度(km)*1.5 - [车辆当前位置到pickup距离 (km)]*0.12  
        充电匹配收益 = 0.2*(100-电量) - [车辆当前位置到充电站距离 (km)]*0.12  
        对于电量低于15%的车辆，强制其只选择充电任务。
        """
        available_vehicles = self.get_available_vehicles()
        available_orders = self.get_available_orders()
        charge_coeff = 0.15

        model = gp.Model("Scheduler")
        model.setParam('OutputFlag', 0)

        vehicle_ids = [v.vid for v in available_vehicles]
        order_ids = [o.oid for o in available_orders]
        station_ids = [s.cid for s in self.stations if len(s.charging_vehicles) < 5]

        vehicle_map = {v.vid: v for v in available_vehicles}
        order_map = {o.oid: o for o in available_orders}
        station_map = {s.cid: s for s in self.stations if len(s.charging_vehicles) < 5}

        # 计算订单匹配收益
        order_profit = {}
        for v in available_vehicles:
            for o in available_orders:
                pickup_distance = haversine_distance(v.position, o.pickup)
                profit = o.length * 1.5 - pickup_distance * 0.12
                order_profit[(v.vid, o.oid)] = profit

        # 计算充电匹配收益
        charge_profit = {}
        for v in available_vehicles:
            for s in station_map.values():
                station_distance = haversine_distance(v.position, s.position)
                profit = charge_coeff * (100 - v.battery) - station_distance * 0.12
                charge_profit[(v.vid, s.cid)] = profit

        # 定义决策变量：x[v,o] 表示车辆 v 分配给订单 o；y[v,s] 表示车辆 v 分配给充电站 s
        x = model.addVars(vehicle_ids, order_ids, vtype=GRB.BINARY, name="x")
        y = model.addVars(vehicle_ids, station_ids, vtype=GRB.BINARY, name="y")

        # 每辆车只能执行一个任务
        for v in vehicle_ids:
            model.addConstr(gp.quicksum(x[v, o] for o in order_ids) + gp.quicksum(y[v, s] for s in station_ids) <= 1)

        # 每个订单最多分配给一辆车
        for o in order_ids:
            model.addConstr(gp.quicksum(x[v, o] for v in vehicle_ids) <= 1)

        # 每个充电站容量限制：新分配车辆加上已在站车辆不超过 5
        for s in station_ids:
            capacity_left = 5 - len(station_map[s].charging_vehicles)
            model.addConstr(gp.quicksum(y[v, s] for v in vehicle_ids) <= capacity_left)

        # 对于电量低于15%的车辆，强制只选择充电任务
        for v in vehicle_ids:
            if vehicle_map[v].battery < 15:
                model.addConstr(gp.quicksum(x[v, o] for o in order_ids) == 0)
                model.addConstr(gp.quicksum(y[v, s] for s in station_ids) == 1)

        obj_order = gp.quicksum(order_profit[(v, o)] * x[v, o] for v in vehicle_ids for o in order_ids)
        obj_charge = gp.quicksum(charge_profit[(v, s)] * y[v, s] for v in vehicle_ids for s in station_ids)
        model.setObjective(obj_order + obj_charge, GRB.MAXIMIZE)

        model.optimize()

        if model.solCount == 0:
            print("No feasible solution found in current cycle.")
            return

        # 根据求解结果更新车辆分配
        for v in vehicle_ids:
            v_obj = vehicle_map[v]
            assigned_order = None
            for o in order_ids:
                if x[v, o].X > 0.5:
                    assigned_order = order_map[o]
                    break
            if assigned_order is not None:
                distance = haversine_distance(v_obj.position, assigned_order.pickup)
                travel_time = math.ceil(distance / TRAVEL_SPEED) if distance > 0 else 1
                v_obj.trip_start_position = v_obj.position
                v_obj.trip_travel_time = travel_time
                v_obj.trip_travel_remaining = travel_time
                v_obj.current_order = assigned_order
                v_obj.status = 'to-trip'
                assigned_order.status = 'assigned'
                self.total_profit += order_profit[(v, assigned_order.oid)]
                continue

            for s in station_ids:
                if y[v, s].X > 0.5:
                    station_obj = station_map[s]
                    d = haversine_distance(v_obj.position, station_obj.position)
                    travel_time = math.ceil(d / TRAVEL_SPEED) if d > 0 else 1
                    v_obj.charge_start_position = v_obj.position
                    v_obj.charge_target = station_obj
                    v_obj.charge_travel_time = travel_time
                    v_obj.charge_travel_remaining = travel_time
                    v_obj.status = 'to-charge'
                    self.total_profit += charge_profit[(v, s)]
                    break

    def run_simulation(self, total_cycles=12):
        for cycle in range(total_cycles):
            self.current_cycle = cycle
            self.add_new_orders(cycle)
            self.update_states()
            self.schedule()
            print(f"Cycle {cycle} completed. Total profit: {self.total_profit:.2f}")
            print("Vehicle Schedules:")
            for v in self.vehicles:
                schedule_str = f"Vehicle {v.vid}: Position {v.position}, Battery: {v.battery:.1f}, Status: {v.status}"
                if v.status == 'to-trip':
                    schedule_str += f", Heading to Pickup: {v.current_order.pickup if v.current_order else 'None'}"
                elif v.status == 'on-trip':
                    order_info = v.current_order.oid if v.current_order else "None"
                    schedule_str += f", On Trip (Order {order_info})"
                elif v.status == 'to-charge':
                    station_info = v.charge_target.cid if v.charge_target else "None"
                    schedule_str += f", Heading to Charging Station: {station_info}"
                elif v.status.startswith('charging'):
                    station_info = v.charging_station.cid if v.charging_station else "None"
                    schedule_str += f", Charging at Station: {station_info}"
                print(schedule_str)
            print("-" * 50)
            # 模拟结束后，统计完成订单数量和成功匹配订单数量
        served_orders = [o for o in self.all_orders if o.status == 'completed']
        matched_orders = [o for o in self.all_orders if o.status in ['assigned', 'completed']]
        print(f"Total orders served (completed): {len(served_orders)}")
        print(f"Total orders matched: {len(matched_orders)}")

if __name__ == "__main__":
    scheduler = Scheduler()
    scheduler.initialize(n_vehicles=700, n_stations=100, excel_path=r"C:\D学习\小论文\数据\成都一天.xlsx")
    scheduler.run_simulation(total_cycles=12)
