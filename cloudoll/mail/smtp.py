#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "chuchur"

"""
MAIL = {
    "smtp_server": "smtp.qq.com",
    "account": "123456789@qq.com",
    "account_name": "chuchur",
    "password": "abcdefg",
    "prot": 465,  # 587
    "debug_level": 1,
}

m = smtp.Mail(**MAIL)
# 标题
m.subject = "test title"
# 正文
m.content = "long long ago..."

# 嵌入html 和 html 调用附件
m.addfile("/home/chuchur/img/a.jpg") # cid 0
m.addfile("/home/chuchur/img/b.jpg") # cid 1
m.addhtml("<html><body><h1>Hello</h1>" + '<p><img src="cid:0"><img src="cid:1"></p>' + "</body></html>")

# 多个收件人
m.add_to_addr("李彦宏", "liyanhong@baidu.com")
m.add_to_addr("马云", "jackma@alibaba.com")

# 附件
m.addfile(filepathA)
m.addfile(filepathB)

# 发送
m.send()

"""

import smtplib, os
from email import encoders
from email.header import Header
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

from email.utils import parseaddr, formataddr
import mimetypes
from ..logging import info, error


def _format_addr(s):
    name, addr = parseaddr(s)
    return formataddr((Header(name, "utf-8").encode(), addr))


class Client(object):
    def __init__(self, **config):
        self._content = None
        self._subject = None
        smtp_server = config.get("smtp_server")
        debug_level = config.get("debug_level", 1)
        port = config.get("port", 25)
        self._account = config.get("account", "")
        self._account_name = config.get("account_name", "")
        self._password = config.get("password", "")
        self._server = smtplib.SMTP_SSL(smtp_server, port)
        # self._server.starttls()  # 调用starttls()方法加密
        self._server.set_debuglevel(debug_level)  # 打印出和SMTP服务器交互的所有信息
        self._msg = MIMEMultipart()
        self._to_addr = []
        self._mime_type = "plain"  # 'html'
        self._file_index = 0

    def _login(self):
        try:
            account = self._account
            password = self._password
            if account is None or password is None:
                raise KeyError("请设置账号密码")
            info("登录中...")
            self._server.login(account, password)
        except BaseException as e:
            error(e)
            raise

    def send(self):
        """
        发送邮件
        """
        try:
            self._login()
            # msg = MIMEText(self._content, "plain", "uft-8")
            msg = self._msg
            msg["From"] = _format_addr("%s <%s>" % (self._account_name, self._account))
            to = []
            for t in self._to_addr:
                to.append("%s <%s>" % (t["name"], t["addr"]))
            msg["To"] = _format_addr(",".join(to))

            # 邮件标题
            msg["Subject"] = Header(self._subject, "utf-8").encode()

            # 邮件正文
            msg.attach(MIMEText(self._content, self._mime_type, "utf-8"))
            to_addr = list(map(lambda x: x["addr"], self._to_addr))
            self._server.sendmail(self._account, to_addr, msg.as_string())
            self._server.quit()
        except BaseException as er:
            error(er)

    def add_to_addr(self, nick, addr):
        """
        添加收件人
        :params nick 收件人昵称
        :params addr 收件人地址
        """
        if addr is None:
            raise KeyError("请输入邮箱地址")
        obj = {"name": nick, "addr": addr}
        self._to_addr.append(obj)

    def addhtml(self, htmltext):
        """
        添加html正文
        :params htmltext html正文内容
        """
        self._msg.attach(MIMEText(htmltext, "html", "utf-8"))

    def addfile(self, filepath):
        """
        添加附件
        :params filepath 附件绝对路径
        """
        index = self._file_index
        with open(filepath, "rb") as f:
            mime_type = ""
            mime_types = mimetypes.guess_type(filepath)  # image/png
            if len(mime_types) > 0:
                mime_type = mime_types[0]
            else:
                error("无法匹配附件类型,可以尝试安装httpd服务")
            ## 这里如果拿不到type 需要安装httpd ,dnf install httpd
            [t, n] = mime_type.split("/")
            filename = os.path.basename(filepath)  # 'a.txt'
            # 设置附件的MIME和文件名
            mime = MIMEBase(t, n, filename=filename)
            # 加上头信息
            mime.add_header("Content-Disposition", "attachment", filename=filename)
            mime.add_header("Content-ID", "<%s>" % index)
            mime.add_header("X-Attachment-Id", "%s" % index)
            # 把附件内容读入
            mime.set_payload(f.read())
            # 用Base64编码
            encoders.encode_base64(mime)

            # 添加到MIMEMultipart
            self._msg.attach(mime)
            self._file_index += 1

    @property
    def mime_type(self):
        return self._mime_type

    @mime_type.setter
    def mime_type(self, value):
        self._mime_type = value

    @property
    def subject(self):
        """
        邮件标题内容
        """
        return self._subject

    @subject.setter
    def subject(self, value):
        """
        邮件标题内容
        :params value 标题内容
        """
        self._subject = value

    @property
    def content(self):
        """
        邮件正文内容
        """
        return self._content

    @content.setter
    def content(self, value):
        """
        邮件正文内容
        :params value 正文内容
        """
        self._content = value
