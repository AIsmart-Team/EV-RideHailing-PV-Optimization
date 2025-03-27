# EV-RideHailing-PV-Optimization
用于优化智能光伏微电网中的电动网约车调度和充电策略框架，以提高可再生能源利用率和电网稳定性
# Carbon Reduction Potential of Electric Ride-hailing Scheduling in Intelligent Photovoltaic Microgrids

## Overview
该存储库包含一种新型电动车调度框架，用于与光伏能源系统协调优化电动网约车服务。该项目融合三方效益，探索电动汽车的智能调度如何提高电网稳定性，同时最大限度地提高可再生能源利用率。
## Key Contributions

- 开发光伏能源场景中动态网约车和充电耦合调度的仿真优化框架
- 调查电动网约车在减少碳排放和平衡电网负载方面的潜力
- 将绿色能源纳入电动汽车充电调度框架
- 创建一个考虑多个利益相关者（网约车平台、电网运营商、消费者）利益的模型
- 分析不同区域需求、时间段和天气条件下的性能

## Methodology

我们的研究包括:
- 动态车辆充电和网约车调度优化
- 区域需求建模和供需平衡注意事项
- 集成光伏发电模式和电网负载曲线
- 多方利益相关者利益分析
- 使用关键指标（包括 PV 利用率、调峰效益和碳减排量）进行性能评估

## Key Findings
研究结果发现:
- 光伏利用率提高 32.8%
- 平台总收益提高 6.62%
- 晴天时，调峰和填谷效果为 8.82%
- 通过协调的电动汽车调度，减少碳排放的潜力巨大

## Project Structure
```
EV-RideHailing-PV-Optimization/
├── configs.py
├── data/
│   ├── road_network/                # 路网数据
│   │   ├── road_nodes.csv           # 路网节点数据
│   │   └── road_edges.csv           # 路网边数据
│   └── simulation/                  # 模拟数据
│       ├── orders.xlsx              # 原始订单数据
│       └── charging_stations.json   # 充电站配置
├── simulation/                      # 新增调度模块
│   ├── __init__.py
│   ├── core/
│   │   ├── scheduler.py             # 调度核心算法
│   │   ├── optimizer.py             # Gurobi优化模型
│   │   └── state_manager.py         # 状态更新逻辑
│   ├── models/
│   │   ├── vehicle.py               # 车辆类定义
│   │   ├── order.py                 # 订单类定义
│   │   └── station.py               # 充电站类
│   └── analysis/
│       ├── metrics.py               # 模拟评估指标
│       └── visualizer.py            # 模拟结果可视化
├── outputs/
│   └── simulation/                  # 新增模拟输出
│       ├── trajectories/            # 车辆轨迹数据
│       ├── assignments/             # 订单分配记录
│       └── reports/                 # 分析报告
├── run_simulation.py                # 模拟入口脚本
└── requirements.txt
```
## 环境要求
- 此脚本在annaconda环境中运行，python版本：3.11.4.
- 需要注意的是：本代码求解使用gurobi求解器Version 12.0.1，使用者需先下载求解器并安装在环境中并成功激活。
- gurobi下载官网：https://www.gurobi.com/
- gurobi激活教程方法：https://zhuanlan.zhihu.com/p/24819586963
### 依赖包和库

```bash
pip install gurobipy
```
## 使用说明
- 准备数据完成后，直接运行调度.py即可
#### 数据准备
- 将需要使用的数据地址更改到调度.py中，具体位于main.py：scheduler.initialize(n_vehicles=700, n_stations=100, excel_path=r"你的文件位置")
- 如果需要更改充电站车辆等设置请更改configs.py中的具体配置

#### 模块说明
- 1.configs.py：
    ###### 时空参数
    CYCLE_DURATION = 300  # 秒
    TRAVEL_SPEED = 40 / 12  # km/cycle
    MAX_CYCLES = 12
    
    ###### 车辆参数
    INIT_BATTERY = (30, 100)
    BATTERY_DECAY = 5
    CHARGE_THRESHOLD = 20
    
    ###### 经济模型
    ORDER_PRICE = lambda x: x * 1.5  # 订单计价函数
    COST_PER_KM = 0.12
    
    ###### 优化参数
    GUROBI_PARAMS = {
        'OutputFlag': 0,
        'TimeLimit': 60
    }

- 2.vehicle.py：
  定义车辆初始位置，初始电量，并确定车辆位置更新原则
  
- 3.order.py：
  定义订单位置，计算订单需要运行时间周期
  
- 4.station.py：
  定义充电站位置，个数，充电站最大承载能力
  
- 5.scheduler.py
  调度核心逻辑：
    ###### 周期开始，判断车辆状态订单状态后选择可调度的订单和车辆。通过目标函数进行调度分配，更新状态（未参与调度的车辆判断经过这一周期后状态是否有变化，如果经过了这个周期也就是到下一周期开始时的时间节点，订单完成了那么状态会从接送订单中变为空闲；如果经过了这一周期电量超过了30，那么状态会从充电中（不可用）变为充电中（可用）。
    ###### 参与调度的车辆进行状态更新：判断到下一周期开始时是什么状态，被分配到订单的车辆，如果下一周期开始时就能完成这个订单那么最终会变为空闲，当然大部分情况一个周期是无法完成订单的，所以基本都会变成接送订单中。被分配到充电的车辆，如果下一周期开始时也就是经过了这一个周期电量就能充到30以上，那么最终状态变为充电中（可用），否则为充电中（不可用）。这样通过分别更新参与调度的车辆和不参与调度的车辆就完成所有车辆这个周期的状态更新。
    ###### 订单更新：对所有订单进行判断，车辆接到订单后到目前时间节点，是否已经达到订单时长，达到则为已完成，否则为未完成），下一周期开始，利用上一周期更新的状态判断可调度车辆和订单，进行根据目标函数的调度匹配，更新状态...。

  
- 6.state_manager.py
- 
