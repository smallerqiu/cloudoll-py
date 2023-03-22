#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur/chuchur.com"

import hashlib, hmac, time, base64, logging, requests as http


class Client(object):
    def __init__(self, **kw):
        self._webhook = kw.get("webhook")
        self._secret = kw.get("secret")

    def _get_sign(self):
        secret = self._secret
        if not secret:
            logging.error("缺少secret")
            return None, None
        # 拼接timestamp和secret
        timestamp = int(time.time())
        string_to_sign = "{}\n{}".format(timestamp, secret)
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
        ).digest()

        # 对结果进行base64处理
        sign = base64.b64encode(hmac_code).decode("utf-8")

        return timestamp, sign

    def send(self, data: dict):
        """
        发送除签名外的自定义消息结构体
        :params data 自定义消息结构体
        """
        webhook = self._webhook
        if not webhook:
            logging.error("缺少webhook")
            return False
        timestamp, sign = self._get_sign()
        if not timestamp or not sign:
            return False
        result = http.post(
            url=webhook,
            json={"timestamp": timestamp, "sign": sign, **data},
        )
        if result:
            res = result.json()
            if res["StatusCode"] == 0:
                logging.info("发送成功")
                return False
            else:
                logging.info("发送失败！")
                return True

    def send_text(self, text: str):
        """
        发送文本消息
        :params text 消息内容
        """
        return self.send(
            data={
                "msg_type": "text",
                "content": {"text": text},
            }
        )

    def send_card(self, **kw):
        """
        发送卡片消息
        :params content 卡片内容,str
        :params elements 参见 ：https://open.feishu.cn/document/ukTMukTMukTM/uMjNwUjLzYDM14yM2ATN
        :params template 标题背景颜色 blue|wathet|truquoise|green|yellow|orange|red|carmine|violet|purple|indigo|grey
        :params i18n 多语言 {'zh_cn':'...'}
        """
        content = kw.get("content", "")
        i18n = kw.get("i18n", {})
        elements = kw.get("elements", [])
        template = kw.get("template", "blue")
        return self.send(
            data={
                "msg_type": "interactive",
                "card": {
                    "config": {
                        "wide_screen_mode": True,
                        "enable_forward": True,
                        "update_multi": True,
                    },
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": content,
                            "i18n": i18n,
                        },
                        "template": template,
                    },
                    "elements": elements,
                },
            }
        )
