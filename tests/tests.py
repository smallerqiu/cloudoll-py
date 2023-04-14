from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker

# 生成基类 所有表构建的类都是基类之上的 继承这个基类
Base = declarative_base()


class Student(Base):
    __tablename__ = 'student'  # 表名

    id = Column(Integer, primary_key=True)
    name = Column(String)
    age = Column(Integer, default=0)  # 默认0
    score = Column(Integer, default=60)  # 默认60

