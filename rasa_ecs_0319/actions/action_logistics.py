from datetime import datetime
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher
from sqlalchemy.orm import joinedload

from actions.db import SessionLocal
from actions.db_table_class import LogisticsCompany, OrderInfo, Logistics, LogisticsComplaint, LogisticsComplaintsRecord


class GetLogisticsCompanys(Action):
    """
    查询数据库，获取支持的快递公司列表
    """

    def name(self) -> Text:
        return "action_get_logistics_companys"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # 查询mysql中的logistics_company表，返回结果给用户
        with SessionLocal() as session:
            logistics_companys = session.query(LogisticsCompany).all()

        # 封装返回的数据格式
        message = ["支持的快递有:"]
        message.extend([f"- {i.company_name}" for i in logistics_companys])

        # 返回封装的数据格式给用户
        dispatcher.utter_message(text="\n".join(message))

        # 当需要设置slot的值时，必须在return当中传
        return []


class GetLogisticsInfo(Action):
    """
    根据指定的订单id，查询详细的物流信息
    """

    def name(self) -> Text:
        return "action_get_logistics_info"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # 1、从槽中获取指定的订单id
        order_id = tracker.get_slot("order_id")
        # 2、查询mysql中的物流信息、订单明细，关联订单表、物流表、订单明细表
        with SessionLocal() as session:
            order_info = (
                session.query(OrderInfo)
                .options(joinedload(OrderInfo.logistics))
                .options(joinedload(OrderInfo.order_detail))
                .filter_by(order_id=order_id)
                .first()
            )
        # 3、按要求封装返回的消息
        logistics = order_info.logistics[0]  # 一个订单，只有一个物流，返回的是list，直接取0即可
        message = [f"- **订单ID**：{order_id}"]
        message.extend(
            [f"  - {order_detail.sku_name} × {order_detail.sku_count}" for order_detail in order_info.order_detail]
        )
        message.append(f"- **物流ID**：{logistics.logistics_id}")
        message.append("- **物流信息**：")
        message.append("  - " + "\n  - ".join(logistics.logistics_tracking.split("\n")))

        # 4、返回封装的数据格式给用户
        dispatcher.utter_message("\n".join(message))

        # 5、将物流ID保存到slot中，方便其他流程使用
        return [SlotSet("logistics_id", logistics.logistics_id)]


class AskLogisticsComplaint(Action):
    """
    查询数据库中常见的投诉原因，返回多个button给用户选择
    """

    def name(self) -> Text:
        return "action_ask_logistics_complaint"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # 1、查询指定物流id对应的物流信息
        logistics_id = tracker.get_slot("logistics_id")

        with SessionLocal() as session:
            logistics = session.query(Logistics).filter_by(logistics_id=logistics_id).first()

        # 2、判断当前物流是处于 已发货、还是已签收状态，通过 delivered_time字段判断
        status = "已发货" if logistics.delivered_time is None else "已签收"

        # 3、查询 logistics_complaint 表，获取常见投诉原因
        with SessionLocal() as session:
            logistics_complaints = session.query(LogisticsComplaint).filter_by(logistics_status=status).all()

        # 4、封装返回的信息和buttons
        buttons = [
            {"title": i.logistics_complaint, "payload": f"/SetSlots(logistics_complaint={i.logistics_complaint})"}
            for i in logistics_complaints
        ]
        # 添加“其他”和“取消投诉”的button
        buttons.append({"title": "其他", "payload": "/SetSlots(logistics_complaint=other)"})
        buttons.append({"title": "取消投诉", "payload": "/SetSlots(logistics_complaint=false)"})

        # 5、发送结果
        dispatcher.utter_button_message(text="请选择要反馈的问题：", buttons=buttons)

        return []


class RecordLogisticsComplaint(Action):
    """
    保存用户的投诉物流id、投诉原因 到mysql中
    """

    def name(self) -> Text:
        return "action_record_logistics_complaint"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        events = []
        # 1、从槽中获取投诉的物流ID和投诉内容
        logistics_id = tracker.get_slot("logistics_id")
        logistics_complaint = tracker.get_slot("logistics_complaint")

        # 2、如果投诉内容为其他，从最新消息中获取
        if logistics_complaint == "other":
            # 2.1 通过tracker获取最新消息的text
            logistics_complaint = tracker.latest_message["text"]
            # 2.2 将投诉内容存入槽logistics_complaint中
            events.append(SlotSet("logistics_complaint", logistics_complaint))

        # 3、构造写入 logistics_complaints_record 表的数据
        with SessionLocal() as session:
            session.add(
                LogisticsComplaintsRecord(
                    logistics_id=logistics_id,
                    logistics_complaint=logistics_complaint,
                    complaint_time=datetime.now(),
                    user_id=tracker.get_slot("user_id"),
                )
            )
            # 4、执行写入
            session.commit()

        # 5、给用户返回消息
        dispatcher.utter_message(text="您的投诉已经收到，我们会尽快处理。")

        return events


# from typing import Any, Dict, List, Text
#
# from rasa_sdk import Action, Tracker
# from rasa_sdk.events import SlotSet
# from rasa_sdk.executor import CollectingDispatcher
#
# from datetime import datetime
# from .db import SessionLocal
# from .db_table_class import (
#     LogisticsCompany,
#     OrderInfo,
#     Logistics,
#     LogisticsComplaint,
#     LogisticsComplaintsRecord,
# )
# from sqlalchemy.orm import joinedload
#
#
# class GetLogisticsCompanys(Action):
#     """
#     查询支持的快递公司，注意以下要求：
#     1、name()返回要与domain_logistics中的action名称一致
#     """
#
#     def name(self) -> str:
#         return "action_get_logistics_companys"
#
#     def run(
#         self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]
#     ) -> List[Dict[Text, Any]]:
#         # 1、获取快递公司列表：查询LogisticsCompany表
#         with SessionLocal() as session:
#             logistics_companys = session.query(LogisticsCompany).all()
#         # 2、按照company_name字段，拼接快递公司名称
#         logistics_companys = "".join(
#             [f"- {i.company_name}\n" for i in logistics_companys]
#         )
#         # 3、如果没有查询到快递公司名称，返回“- 无”
#         if logistics_companys == "":
#             logistics_companys = "- 无"
#         # 4、返回支持的快递公司名称
#         dispatcher.utter_message(f"支持的快递有:\n{logistics_companys}")
#         return []
#
#
# class GetLogisticsInfo(Action):
#     """
#     查询指定订单id的物流信息，注意以下要求：
#     1、name()返回要与domain_logistics中的action名称一致
#     """
#
#     def name(self) -> str:
#         return "action_get_logistics_info"
#
#     def run(
#         self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]
#     ) -> List[Dict[Text, Any]]:
#         # 1、从 slot 中获取 订单ID
#         order_id = tracker.get_slot("order_id")
#
#         # 2、查询指定order_id的订单信息，包括订单详情order_detail、物流信息logistics
#         with SessionLocal() as session:
#             order_info = (
#                 session.query(OrderInfo)
#                 .options(joinedload(OrderInfo.logistics))
#                 .options(joinedload(OrderInfo.order_detail))
#                 .filter_by(order_id=order_id)
#                 .first()
#             )
#
#         # 3、获取订单物流信息结果，按照需求格式拼接返回的message
#         logistics = order_info.logistics[0]
#         # 拼接订单id
#         message = [f"- **订单ID**：{order_id}"]
#         # 拼接sku名称和对应的数量
#         message.extend(
#             [
#                 f"  - {order_detail.sku_name} × {order_detail.sku_count}"
#                 for order_detail in order_info.order_detail
#             ]
#         )
#         # 拼接物流id
#         message.append(f"- **物流ID**：{logistics.logistics_id}")
#         # 拼接“物流信息”标题
#         message.append("- **物流信息**：")
#         # 拼接物流详情，对logistics表的logistics_tracking字段按照换行符进行分割
#         message.append("  - " + "\n  - ".join(logistics.logistics_tracking.split("\n")))
#
#         # 4、返回拼接后的message
#         dispatcher.utter_message("\n".join(message))
#
#         # 5、将物流id存入槽中，SlotSet事件必须作为run方法的返回值
#         return [SlotSet("logistics_id", logistics.logistics_id)]
#
#
# class AskLogisticsComplaint(Action):
#     """
#     询问投诉物流的原因：查询和展示指定物流id的物流信息，之后列出投诉该物流原因的button选项。注意以下要求：
#     1、name()返回要与domain_logistics中的action名称一致
#     """
#
#     def name(self) -> str:
#         return "action_ask_logistics_complaint"
#
#     def run(
#         self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]
#     ) -> List[Dict[Text, Any]]:
#         # 1、根据指定的logstics_id查询对应物流信息
#         # 1.1 从槽中获取投诉的物流单号
#         logistics_id = tracker.get_slot("logistics_id")
#         # 1.2 查询Logistics表中指定logistics_id的物流信息
#         with SessionLocal() as session:
#             logistics = (
#                 session.query(Logistics).filter_by(logistics_id=logistics_id).first()
#             )
#
#         # 2、根据物流状态获取可用的投诉信息
#         # 2.1 判断物流状态：有物流信息只可能是已发货或者已签收。delivered_time为None说明是已发货，否则是已签收
#         logistics_status = "已发货" if logistics.delivered_time is None else "已签收"
#         # 2.2 获取该状态下可用的投诉信息，根据物流状态查询LogisticsComplaint表
#         with SessionLocal() as session:
#             logistics_complaints = (
#                 session.query(LogisticsComplaint)
#                 .filter_by(logistics_status=logistics_status)
#                 .all()
#             )
#
#         # 3. 拼接button选项
#         # 3.1 拼接常见原因button：title 为物流投诉原因，payload 为 SetSlots(logistics_complaint=物流投诉原因)
#         buttons = [
#             {
#                 "title": f"{i.logistics_complaint}",
#                 f"payload": f"/SetSlots(logistics_complaint={i.logistics_complaint})",
#             }
#             for i in logistics_complaints
#         ]
#         # 3.2 button添加一个其他选项和取消投诉选项
#         buttons.extend(
#             [
#                 {"title": "其他", "payload": f"/SetSlots(logistics_complaint=other)"},
#                 {
#                     "title": "取消投诉",
#                     "payload": f"/SetSlots(logistics_complaint=false)",
#                 },
#             ]
#         )
#
#         # 4. 返回button选项
#         dispatcher.utter_message(text="请选择要反馈的问题", buttons=buttons)
#         return []
#
#
# class RecordLogisticsComplaint(Action):
#     """
#     记录投诉信息，注意以下要求：
#     1、name()返回要与domain_logistics中的action名称一致
#     """
#
#     def name(self) -> str:
#         return "action_record_logistics_complaint"
#
#     def run(
#         self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[str, Any]
#     ) -> List[Dict[Text, Any]]:
#         events = [] # 返回给用户的事件，需要list类型
#         # 1、从槽中获取投诉的物流ID和投诉内容
#         logistics_id = tracker.get_slot("logistics_id")
#         logistics_complaint = tracker.get_slot("logistics_complaint")
#
#         # 2、如果投诉内容为其他，从最新消息中获取
#         if logistics_complaint == "other":
#             # 2.1 通过tracker获取最新消息的text
#             logistics_complaint = tracker.latest_message["text"]
#             # 2.2 将投诉内容存入槽logistics_complaint中
#             events.append(SlotSet("logistics_complaint", logistics_complaint))
#
#         # 3、返回给用户消息，表示已收到指定物流id的投诉原因logistics_complaint
#         dispatcher.utter_message(
#             text=f"已收到您反馈的 {logistics_id} 的 {logistics_complaint} 问题，我们会尽快处理"
#         )
#
#         # 4、将投诉信息存入数据库，向LogisticsComplaintsRecord表中插入一条记录
#         with SessionLocal() as session:
#             session.add(
#                 LogisticsComplaintsRecord(
#                     logistics_id=logistics_id,
#                     logistics_complaint=logistics_complaint,
#                     complaint_time=datetime.now(),
#                     user_id=tracker.get_slot("user_id"),
#                 )
#             )
#             # 提交变更
#             session.commit()
#
#         # 5、返回事件。SlotSet事件必须作为run方法的返回值
#         return events
