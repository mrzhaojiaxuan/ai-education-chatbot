"""
订单相关 Action 实现模块

本模块包含以下核心功能：
1. 订单查询：根据不同条件查询用户订单列表
2. 订单详情：获取并展示订单详细信息
3. 修改订单收货信息：支持修改收货人、电话、地址等信息
4. 取消订单：支持取消待支付/待发货状态的订单

技术栈：
- Rasa SDK：自定义 Action 开发框架
- SQLAlchemy：数据库 ORM 操作
- MySQL：订单数据存储
"""

from datetime import datetime, timedelta
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet, ActionExecutionRejected
from rasa_sdk.executor import CollectingDispatcher
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

from actions.db import SessionLocal
from actions.db_table_class import OrderInfo, Postsale, ReceiveInfo, Region
from uuid import uuid4


class AskOrderID(Action):
    """
    查询订单ID，返回订单列表按钮供用户选择

    根据槽 `goto` 的值，动态构建不同的查询条件，支持以下场景：
    - action_ask_order_id_shipped: 查询已发货订单
    - action_ask_order_id_shipped_delivered: 查询已发货/已签收订单
    - action_ask_order_id_before_completed_3_days: 查询进行中或3日内完成订单
    - action_ask_order_id_before_delivered: 查询已签收之前状态订单
    - action_ask_order_id_before_shipped: 查询已发货之前状态订单
    - action_ask_order_id_after_delivered: 查询已签收及之后状态订单
    """

    def name(self) -> Text:
        """
        返回 Action 名称，必须与 domain_order.yml 中定义的名称一致
        """
        return "action_ask_order_id"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """
        执行 Action 主逻辑

        :param dispatcher: 消息发送器，用于向用户发送消息和按钮
        :param tracker: 对话追踪器，用于获取槽值和对话历史
        :param domain: 域配置，包含槽、响应、意图等定义
        :return: 事件列表，用于更新槽值或控制对话流程
        """
        # 初始化事件列表，用于存储需要返回的事件
        events = []

        # 1、查询数据库中的订单信息
        # 使用 SessionLocal 创建数据库会话
        with SessionLocal() as session:
            order_infos = (
                session.query(OrderInfo)
                .join(OrderInfo.order_status_)  # 关联订单状态表，获取订单状态名称
                .options(joinedload(OrderInfo.order_detail))  # 预加载订单明细表，避免 N+1 查询问题
                .filter(self.get_query_condition(tracker))  # 根据槽值动态构建过滤条件
                .all()  # 获取所有匹配的订单
            )

        # 2、根据查询结果数量，分情况处理
        order_nums = len(order_infos)

        # 2.1 如果只有一个订单，直接询问用户是否查询此订单
        if order_nums == 1:
            order_info = order_infos[0]
            # 拼接订单信息：订单状态、订单ID、订单明细
            message = [
                "查找到一个订单",
                f"[{order_info.order_status}]**订单ID**：{order_info.order_id}",
            ]
            # 遍历订单明细，添加商品名称和数量
            for order_detail in order_info.order_detail:
                message.append(f"- {order_detail.sku_name} × {order_detail.sku_count}")
            # 发送消息和按钮，供用户选择确认或返回
            dispatcher.utter_message(
                text="\n".join(message),
                buttons=[
                    {
                        "title": "确认",
                        "payload": f"/SetSlots(order_id={order_info.order_id})",  # 设置订单ID槽值
                    },
                    {"title": "返回", "payload": "/SetSlots(order_id=false)"},  # 设置订单ID为false
                ],
            )

        # 2.2 如果有多个订单，列出所有订单供用户选择
        elif order_nums > 1:
            # 遍历订单列表，生成按钮
            buttons = [
                {
                    "title": "\n".join(
                        [
                            f"[{order_info.order_status}]订单ID：{order_info.order_id}",
                        ]
                        + [
                            f"- {order_detail.sku_name} × {order_detail.sku_count}"
                            for order_detail in order_info.order_detail
                        ]
                    ),
                    "payload": f"/SetSlots(order_id={order_info.order_id})",  # 设置选中的订单ID
                }
                for order_info in order_infos
            ]
            # 添加返回按钮
            buttons.append({"title": "返回", "payload": "/SetSlots(order_id=false)"})
            dispatcher.utter_message(text="请选择订单", buttons=buttons)

        # 2.3 如果没有查询到订单，告知用户并结束流程
        else:
            dispatcher.utter_message(text="暂无订单")
            events.append(SlotSet("order_id", "false"))  # 设置订单ID为false
            events.append(ActionExecutionRejected("action_listen"))  # 打断后续监听动作

        # 返回事件列表
        return events

    def get_query_condition(self, tracker: Tracker):
        """
        根据槽值动态构建数据库查询条件

        :param tracker: 对话追踪器，用于获取用户ID和goto槽值
        :return: SQLAlchemy 查询条件对象
        """
        # 获取用户ID和查询条件标志位
        user_id = tracker.get_slot("user_id")
        goto = tracker.get_slot("goto")

        # 根据 goto 值构建不同的查询条件
        match goto:
            case "action_ask_order_id_shipped":
                # 查询已发货状态的订单
                return and_(
                    OrderInfo.user_id == user_id,
                    OrderInfo.order_status == "已发货",
                )
            case "action_ask_order_id_shipped_delivered":
                # 查询已发货和已签收状态的订单
                return and_(
                    OrderInfo.user_id == user_id,
                    OrderInfo.order_status.in_(["已发货", "已签收"]),
                )
            case "action_ask_order_id_before_completed_3_days":
                # 查询进行中或3日内已完成的订单
                return and_(
                    OrderInfo.user_id == user_id,
                    OrderInfo.order_status != "已取消",
                    or_(
                        OrderInfo.order_status != "已完成",
                        OrderInfo.complete_time > datetime.now() - timedelta(days=3),
                    ),
                )
            case "action_ask_order_id_before_delivered":
                # 查询已签收之前状态的订单（status_code <= 320）
                return and_(
                    OrderInfo.user_id == user_id,
                    OrderInfo.order_status != "已取消",
                    OrderInfo.order_status_.has(status_code=lambda x: x <= 320),
                )
            case "action_ask_order_id_before_shipped":
                # 查询已发货之前状态的订单（status_code <= 310）
                return and_(
                    OrderInfo.user_id == user_id,
                    OrderInfo.order_status != "已取消",
                    OrderInfo.order_status_.has(status_code=lambda x: x <= 310),
                )
            case "action_ask_order_id_after_delivered":
                # 查询已签收及之后状态的订单（status_code >= 330）
                return and_(
                    OrderInfo.user_id == user_id,
                    OrderInfo.order_status != "已取消",
                    OrderInfo.order_status_.has(status_code=lambda x: x >= 330),
                )


class GetOrderDetail(Action):
    """
    获取订单详情，展示订单完整信息

    查询订单的基本信息、订单明细、收货信息、物流信息和售后信息，并以结构化消息形式返回给用户
    """

    def name(self) -> str:
        """
        返回 Action 名称，必须与 domain_order.yml 中定义的名称一致
        """
        return "action_get_order_detail"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[Dict[Text, Any]]:
        """
        执行 Action 主逻辑

        :param dispatcher: 消息发送器
        :param tracker: 对话追踪器
        :param domain: 域配置
        :return: 事件列表
        """
        # 1、获取订单ID槽值
        order_id = tracker.get_slot("order_id")

        # 2、查询订单详情，使用 joinedload 预加载关联表
        with SessionLocal() as session:
            order_info = (
                session.query(OrderInfo)
                .options(joinedload(OrderInfo.order_detail))  # 预加载订单明细
                .options(joinedload(OrderInfo.logistics))  # 预加载物流信息
                .options(joinedload(OrderInfo.receive))  # 预加载收货信息
                .options(joinedload(OrderInfo.order_status_))  # 预加载订单状态
                .filter_by(order_id=order_id)  # 按订单ID查询
                .first()  # 获取单条记录
            )

        # 3、拼接订单信息
        # 3.1 订单基本信息：状态、订单ID、时间信息
        message = [f"- [{order_info.order_status}]**订单ID**：{order_info.order_id}"]
        # 遍历时间字段，只添加非空的时间
        for k, v in {
            "创建时间": order_info.create_time,
            "支付时间": order_info.payment_time,
            "签收时间": order_info.delivered_time,
            "完成时间": order_info.complete_time,
        }.items():
            if v:
                message.append(f"  - {k}：{v}")

        # 3.2 订单明细：商品列表和金额统计
        message.append("- **订单明细**：")
        total_total_amount = 0.0  # 订单总金额
        total_discount_amount = 0.0  # 订单优惠金额
        total_final_amount = 0.0  # 订单实付金额
        # 遍历订单明细，计算金额并拼接信息
        for order_detail in order_info.order_detail:
            message.append(f"  - {order_detail.sku_name} × {order_detail.sku_count} | \
                {order_detail.total_amount}-{order_detail.discount_amount}={order_detail.final_amount}")
            total_total_amount += float(order_detail.total_amount)
            total_discount_amount += float(order_detail.discount_amount)
            total_final_amount += float(order_detail.final_amount)
        # 添加金额合计
        message.append(f"  - **合计**：{total_total_amount}-{total_discount_amount}={total_final_amount}")

        # 3.3 收货信息：收货人、电话、地址
        message.extend(
            [
                "- **收货信息**：",
                f"  - 收货人：{order_info.receive.receiver_name}",
                f"  - 联系电话：{order_info.receive.receiver_phone}",
                f"  - 收货地址：{order_info.receive.receive_province}\
                {order_info.receive.receive_city}\
                {order_info.receive.receive_district}\
                {order_info.receive.receive_street_address}",
            ]
        )

        # 3.4 物流信息：最近物流状态
        logistics = order_info.logistics
        if logistics:
            message.append("- **最近物流信息**：")
            # 取物流追踪信息的最后一条
            message.append(f"  - {logistics[0].logistics_tracking.splitlines()[-1]}")

        # 4、发送订单详情消息
        dispatcher.utter_message(text="\n".join(message))

        # 5、判断是否有售后信息（status_code >= 400 表示售后中）
        if order_info.order_status_.status_code < 400:
            return []

        # 6、查询售后信息
        # 获取所有订单明细ID
        order_detail_ids = [order_detail.order_detail_id for order_detail in order_info.order_detail]
        with SessionLocal() as session:
            # 子查询：按订单明细ID分组，取最新的售后记录（最大创建时间）
            subquery = (
                session.query(
                    Postsale.order_detail_id,
                    func.max(Postsale.create_time).label("max_time"),
                )
                .filter(Postsale.order_detail_id.in_(order_detail_ids))
                .group_by(Postsale.order_detail_id)
                .subquery()
            )
            # 主查询：获取最新售后记录，关联订单明细和物流信息
            postsales = (
                session.query(Postsale)
                .join(
                    subquery,
                    and_(
                        Postsale.order_detail_id == subquery.c.order_detail_id,
                        Postsale.create_time == subquery.c.max_time,
                    ),
                )
                .options(joinedload(Postsale.order_detail))  # 预加载订单明细
                .options(joinedload(Postsale.logistics))  # 预加载物流信息
                .all()
            )

        # 如果没有售后信息，直接返回
        if not postsales:
            return []

        # 7、拼接并发送售后信息
        for postsale in postsales:
            message = [f"- [{postsale.postsale_status}]**售后ID**：{postsale.postsale_id}"]
            message.append("- **订单明细**：")
            message.append(f"  -{postsale.order_detail.sku_name} × {postsale.order_detail.sku_count}")
            message.append(f"- **退款金额**：{postsale.refund_amount}")
            # 获取最新物流信息
            if postsale.logistics:
                # 按创建时间倒序排序，取最新的物流
                postsale.logistics = sorted(postsale.logistics, key=lambda x: x.create_time, reverse=True)
                message.append("- **最近物流信息**：")
                message.append(f"  - {postsale.logistics[0].logistics_tracking.splitlines()[-1]}")
            dispatcher.utter_message(text="\n".join(message))

        return []


class AskReceiveId(Action):
    """
    查询用户现有收货信息，返回按钮供用户选择

    支持以下操作：
    1. 使用现有收货信息：直接关联到订单
    2. 修改并新建收货信息：进入修改流程，允许用户修改收货人、电话、地址
    3. 取消：结束操作

    关键逻辑：在用户选择"修改并新建"之前，先将当前订单的收货信息预填充到槽中，
    用户只需修改变化的字段，其余字段保持原值。
    """

    def name(self) -> str:
        """
        返回 Action 名称，必须与 domain_order.yml 中定义的名称一致
        """
        return "action_ask_receive_id"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[Dict[Text, Any]]:
        """
        执行 Action 主逻辑

        :param dispatcher: 消息发送器
        :param tracker: 对话追踪器
        :param domain: 域配置
        :return: 事件列表，包含预填充的收货信息槽值
        """
        # 1、从槽中获取用户ID和订单ID
        user_id = tracker.get_slot("user_id")
        order_id = tracker.get_slot("order_id")

        # 2、查询用户的收货信息和当前订单的收货信息
        with SessionLocal() as session:
            # 获取用户所有已保存的收货信息
            receive_infos = session.query(ReceiveInfo).filter_by(user_id=user_id).all()
            # 获取当前订单的收货信息
            current_receive_info = session.query(OrderInfo).filter_by(order_id=order_id).first().receive

        # 3、生成收货信息选择按钮
        buttons = []
        for receive_info in receive_infos:
            buttons.append(
                {
                    "title": f"收货人姓名：{receive_info.receiver_name} - \
                    联系电话：{receive_info.receiver_phone} - \
                    收货地址：{receive_info.receive_province}\
                    {receive_info.receive_city}\
                    {receive_info.receive_district}\
                    {receive_info.receive_street_address}",
                    "payload": f"/SetSlots(receive_id={receive_info.receive_id})",
                }
            )

        # 4、添加"修改并新建"和"取消"按钮
        buttons.extend(
            [
                {
                    "title": "修改并新建收货信息",
                    "payload": f"/SetSlots(receive_id=modify)",
                },
                {"title": "取消", "payload": f"/SetSlots(receive_id=false)"},
            ]
        )

        # 5、发送按钮供用户选择
        dispatcher.utter_message(text="请选择现有的收货信息，或修改并新建收货信息", buttons=buttons)

        # 6、预填充当前订单的收货信息到槽中（关键步骤）
        # 用户选择"修改并新建"后，只需修改需要变化的字段，其余字段保持原值
        return [
            SlotSet("receiver_name", current_receive_info.receiver_name),
            SlotSet("receiver_phone", current_receive_info.receiver_phone),
            SlotSet("receive_province", current_receive_info.receive_province),
            SlotSet("receive_city", current_receive_info.receive_city),
            SlotSet("receive_district", current_receive_info.receive_district),
            SlotSet("receive_street_address", current_receive_info.receive_street_address),
        ]


class AskReceiveProvince(Action):
    """
    询问用户选择收货省份

    从数据库中查询所有省份信息，生成按钮供用户选择，实现省市区三级联动的第一步
    """

    def name(self) -> str:
        """
        返回 Action 名称，必须与 domain_order.yml 中定义的名称一致
        """
        return "action_ask_receive_province"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[Dict[Text, Any]]:
        """
        执行 Action 主逻辑

        :param dispatcher: 消息发送器
        :param tracker: 对话追踪器
        :param domain: 域配置
        :return: 事件列表
        """
        # 1、查询数据库中的省份信息，去重
        with SessionLocal() as session:
            provinces = session.query(Region.province).distinct().all()

        # 2、生成省份选择按钮
        buttons = [
            {
                "title": province[0],  # province是元组，取第一个元素
                "payload": f"/SetSlots(receive_province={province[0]})",
            }
            for province in provinces
        ]

        # 3、发送按钮供用户选择
        dispatcher.utter_message(text="请选择省份", buttons=buttons)
        return []


class AskReceiveCity(Action):
    """
    询问用户选择收货城市

    根据用户已选择的省份，查询该省份下的所有城市，生成按钮供用户选择
    """

    def name(self) -> str:
        """
        返回 Action 名称，必须与 domain_order.yml 中定义的名称一致
        """
        return "action_ask_receive_city"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[Dict[Text, Any]]:
        """
        执行 Action 主逻辑

        :param dispatcher: 消息发送器
        :param tracker: 对话追踪器
        :param domain: 域配置
        :return: 事件列表
        """
        # 1、从槽中获取用户已选择的省份
        receive_province = tracker.get_slot("receive_province")

        # 2、查询该省份下的所有城市，去重
        with SessionLocal() as session:
            cities = session.query(Region.city).filter(Region.province == receive_province).distinct().all()

        # 3、生成城市选择按钮
        buttons = [{"title": city[0], "payload": f"/SetSlots(receive_city={city[0]})"} for city in cities]

        # 4、发送按钮供用户选择
        dispatcher.utter_message(text="请选择城市", buttons=buttons)
        return []


class AskReceiveDistrict(Action):
    """
    询问用户选择收货城区

    根据用户已选择的城市，查询该城市下的所有城区，生成按钮供用户选择
    """

    def name(self) -> str:
        """
        返回 Action 名称，必须与 domain_order.yml 中定义的名称一致
        """
        return "action_ask_receive_district"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[Dict[Text, Any]]:
        """
        执行 Action 主逻辑

        :param dispatcher: 消息发送器
        :param tracker: 对话追踪器
        :param domain: 域配置
        :return: 事件列表
        """
        # 1、从槽中获取用户已选择的城市
        receive_city = tracker.get_slot("receive_city")

        # 2、查询该城市下的所有城区，去重
        with SessionLocal() as session:
            districts = session.query(Region.district).filter(Region.city == receive_city).distinct().all()

        # 3、生成城区选择按钮
        buttons = [
            {
                "title": district[0],
                "payload": f"/SetSlots(receive_district={district[0]})",
            }
            for district in districts
        ]

        # 4、发送按钮供用户选择
        dispatcher.utter_message(text="请选择城区", buttons=buttons)
        return []


class AskSetReceiveInfo(Action):
    """
    设置订单收货信息

    支持两种场景：
    1. 首次进入：展示收货信息并询问用户是否确认修改
    2. 确认修改：将收货信息保存到数据库，并更新订单的收货信息关联

    关键逻辑：
    - 如果用户选择"修改并新建"，从槽中读取修改后的信息
    - 如果用户选择现有收货信息，直接使用数据库中的记录
    - 在保存前检查是否已存在相同收货信息，避免重复数据
    """

    def name(self) -> str:
        """
        返回 Action 名称，必须与 domain_order.yml 中定义的名称一致
        """
        return "action_ask_set_receive_info"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[Dict[Text, Any]]:
        """
        执行 Action 主逻辑

        :param dispatcher: 消息发送器
        :param tracker: 对话追踪器
        :param domain: 域配置
        :return: 事件列表
        """
        # 1、从槽中获取关键参数
        receive_id = tracker.get_slot("receive_id")
        set_receive_info = tracker.get_slot("set_receive_info")

        # 2、构建收货信息对象
        if receive_id in ("modify", "modified"):
            # 用户选择修改并新建，从槽中读取修改后的信息
            receive_info = ReceiveInfo(
                receive_id="rec" + uuid4().hex[:16],  # 生成唯一的收货信息ID
                user_id=tracker.get_slot("user_id"),
                receiver_name=tracker.get_slot("receiver_name"),
                receiver_phone=tracker.get_slot("receiver_phone"),
                receive_province=tracker.get_slot("receive_province"),
                receive_city=tracker.get_slot("receive_city"),
                receive_district=tracker.get_slot("receive_district"),
                receive_street_address=tracker.get_slot("receive_street_address"),
            )
        else:
            # 用户选择现有收货信息，从数据库中查询
            with SessionLocal() as session:
                receive_info = session.query(ReceiveInfo).filter_by(receive_id=receive_id).first()

        # 3、确认修改并保存
        if set_receive_info:
            # 获取订单ID
            order_id = tracker.get_slot("order_id")
            with SessionLocal() as session:
                # 查询订单信息
                order_info = session.query(OrderInfo).filter_by(order_id=order_id).first()

                # 如果是新建收货信息，检查是否已存在相同记录（去重）
                if receive_id in ("modify", "modified"):
                    old_receive_info = (
                        session.query(ReceiveInfo)
                        .filter(
                            ReceiveInfo.user_id == receive_info.user_id,
                            ReceiveInfo.receiver_name == receive_info.receiver_name,
                            ReceiveInfo.receiver_phone == receive_info.receiver_phone,
                            ReceiveInfo.receive_province == receive_info.receive_province,
                            ReceiveInfo.receive_city == receive_info.receive_city,
                            ReceiveInfo.receive_district == receive_info.receive_district,
                            ReceiveInfo.receive_street_address == receive_info.receive_street_address,
                        )
                        .first()
                    )
                    if old_receive_info:
                        # 收货信息已存在，使用现有记录
                        receive_info = old_receive_info
                        dispatcher.utter_message(text="此收货信息已存在，将不再重复添加")
                    else:
                        # 收货信息不存在，添加新记录
                        session.add(receive_info)
                        session.flush()  # 刷新获取新记录的ID

                # 更新订单的收货信息关联
                order_info.receive_id = receive_info.receive_id
                # 提交事务
                session.commit()

            # 返回成功消息
            dispatcher.utter_message(text="订单收货信息已修改")
        else:
            # 首次进入，展示收货信息并询问确认
            message = [
                f"- 收货人姓名：{receive_info.receiver_name}",
                f"- 联系电话：{receive_info.receiver_phone}",
                f"- 收货省份：{receive_info.receive_province}",
                f"- 收货城市：{receive_info.receive_city}",
                f"- 收货城区：{receive_info.receive_district}",
                f"- 收货地址：{receive_info.receive_street_address}",
            ]
            dispatcher.utter_message(text="\n".join(message))
            # 发送确认按钮
            dispatcher.utter_message(
                text="是否确认修改？",
                buttons=[
                    {"title": "确认", "payload": "/SetSlots(set_receive_info=true)"},
                    {"title": "取消", "payload": "/SetSlots(set_receive_info=false)"},
                ],
            )

        return []


class CancelOrder(Action):
    """
    取消订单

    将订单状态更新为"已取消"，并更新订单完成时间。
    如果订单状态为"待发货"，额外提示用户退款金额将在24小时内返还。
    """

    def name(self) -> str:
        """
        返回 Action 名称，必须与 domain_order.yml 中定义的名称一致
        """
        return "action_cancel_order"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]) -> List[Dict[Text, Any]]:
        """
        执行 Action 主逻辑

        :param dispatcher: 消息发送器
        :param tracker: 对话追踪器
        :param domain: 域配置
        :return: 事件列表
        """
        # 1、从槽中获取订单ID
        order_id = tracker.get_slot("order_id")

        # 2、更新订单状态
        with SessionLocal() as session:
            order_info = session.query(OrderInfo).filter_by(order_id=order_id).first()
            # 记录原订单状态
            old_order_status = order_info.order_status
            # 更新订单状态为已取消
            order_info.order_status = "已取消"
            # 更新订单完成时间
            order_info.complete_time = datetime.now()
            # 提交事务
            session.commit()

        # 3、生成回复消息
        message = "订单已取消"
        # 如果原状态为待发货，添加退款提示
        if old_order_status == "待发货":
            message += "，退款金额将在24小时内返还您的账户"

        # 4、发送回复消息
        dispatcher.utter_message(text=message)
        return []