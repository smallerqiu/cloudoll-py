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


# 创建引擎 相当于连接
engine = create_engine('mysql+pymysql://test:123456@localhost:3306/testdb')
DBSession = sessionmaker(engine)
session = DBSession()  # 必须实例化对象

# 使用ORM方式对student表做一个查询
students = session.query(Student).limit(10)
session.query(Student).filter(Student.age >= 20)
for s in students:
    print(s.id, s.name, s.age, s.score)

session.close()  # 必须要关闭
