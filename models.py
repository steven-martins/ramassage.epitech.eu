__author__ = 'steven'

# mysql+mysqldb://<user>:<password>@<host>[:<port>]/<dbname>
from sqlalchemy import Column, String, Integer, ForeignKey, UniqueConstraint, Boolean, Enum, DateTime, Text, Table
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
from config import SQL_URI, SQL_DB_URI
import sys
import datetime,json

from flask_dance.consumer.backend.sqla import OAuthConsumerMixin
from flask_login import UserMixin

Base = declarative_base()


def dump_datetime(value, split=True):
    """Deserialize datetime object into string form for JSON processing."""
    if value is None:
        return None
    return [value.strftime("%Y-%m-%d"), value.strftime("%H:%M:%S")] if split else value.strftime("%Y-%m-%d %H:%M:%S")

class User(Base, UserMixin):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    firstname = Column(String(50), nullable=True)
    lastname = Column(String(50), nullable=True)
    login = Column(String(200), unique=True, nullable=False)
    old_login = Column(String(30), nullable=True)

    def __repr__(self):
        return "User('%s', '%s %s', '%s', '%s')" % (self.id,
                                                                                   self.firstname,
                                                                                   self.lastname,
                                                                                   self.login, self.old_login)
    @property
    def serialize(self):
        return {"id": self.id, "firstname": self.firstname, "lastname": self.lastname, "login": self.login, "old_login": self.old_login}

#    @property
#    def is_authenticated(self):
#        return True

#    @property
#    def is_anonymous(self):
#        return False

#    @property
#    def is_active(self):
#        return True

#    def get_id(self):
#        return self.id

class OAuth(Base, OAuthConsumerMixin):
    user_id = Column(Integer, ForeignKey(User.id))
    user = relationship(User)

class Template(Base):
    __tablename__ = 'template'
    id = Column(Integer, primary_key=True)
    codemodule = Column(String(40), nullable=False)
    slug = Column(String(40), nullable=False)
    repository_name = Column(String(90), nullable=True)
    call_moulitriche = Column(Boolean, default=False)
    call_judge = Column(Boolean, default=False)
    judge_uri = Column(String(100), nullable=True)
    judge_rule = Column(String(50), nullable=True)
    judge_preliminary_exec = Column(String(200), nullable=True)
    judge_final_exec = Column(String(200), nullable=True)
    school = Column(Enum("epitech", "coding-academy", "webacademy", "samsung"), default="epitech")
    projects = relationship("Project", backref="template")
    __table_args__ = (UniqueConstraint('codemodule', 'slug', name='_codemodule_slug_uc'),)

    def __repr__(self):
        return "Template('%s', '%s', '%s', repository_name='%s', '%s')" % (
            self.id, self.codemodule, self.slug, self.repository_name, self.school)

    @property
    def serialize(self):
        return {
            "id": self.id,
            "codemodule": self.codemodule,
            "slug": self.slug,
            "repository_name": self.repository_name,
            "call_moulitriche": self.call_moulitriche,
            "call_judge": self.call_judge,
            "judge_uri": self.judge_uri,
            "judge_rule": self.judge_rule,
            "judge_preliminary_exec": self.judge_preliminary_exec,
            "judge_final_exec": self.judge_final_exec,
            "school": self.school
        }

project_assistant_user_table = Table('project_assistant_user', Base.metadata,
    Column('project_id', Integer, ForeignKey('project.id')),
    Column('user_id', Integer, ForeignKey('user.id'))
)


project_templateresp_user_table = Table('project_templateresp_user', Base.metadata,
    Column('project_id', Integer, ForeignKey('project.id')),
    Column('user_id', Integer, ForeignKey('user.id'))
)

project_resp_user_table = Table('project_resp_user', Base.metadata,
    Column('project_id', Integer, ForeignKey('project.id')),
    Column('user_id', Integer, ForeignKey('user.id'))
)

class Project_Student(Base):
    __tablename__ = 'project_student_user'
    project_id = Column(Integer, ForeignKey('project.id'), primary_key=True)
    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
    status = Column(Enum("Succeed", "Failed", "WithErrors"), nullable=True)
    logs = Column(Text, nullable=True)
    begin_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    user = relationship("User")

    def __repr__(self):
        return "Project_Student(project_id='%s', '%s', '%s', logs='%s', begin_date='%s', \
        end_date='%s')" % (self.project_id, self.user.serialize, self.status, self.logs,
                           dump_datetime(self.begin_date, split=False), dump_datetime(self.end_date, split=False))

    @property
    def serialize(self):
        return {
            "project_id": self.project_id,
            "user_id": self.user_id,
            "user": self.user.serialize,
            "status": self.status,
            "logs": self.logs,
            "begin_date": dump_datetime(self.begin_date, split=False),
            "end_date": dump_datetime(self.begin_date, split=False)
        }

class Project(Base):
    __tablename__ = 'project'
    id = Column(Integer, primary_key=True)
    token = Column(String(40), nullable=False)
    template_id = Column(Integer, ForeignKey('template.id'))
    scolaryear = Column(Integer, nullable=False)
    module_title = Column(String(90), nullable=False)
    module_code = Column(String(40), nullable=False)
    instance_code = Column(String(25), nullable=False)
    location = Column(String(20), nullable=False)
    title = Column(String(50), nullable=False)
    deadline = Column(DateTime, nullable=False)
    promo = Column(Integer, nullable=True)
    groups = Column(Text(length=2**19), nullable=True) # json packed groups
    students = relationship("Project_Student", backref=backref("project"),
                            cascade="save-update, merge, delete, delete-orphan")
    resp = relationship("User",
                        secondary=project_resp_user_table,
                        backref="projects_as_resp", cascade="save-update, merge, delete")
    template_resp = relationship("User",
                                 secondary=project_templateresp_user_table,
                                 backref="projects_as_templateresp", cascade="save-update, merge, delete")
    assistants = relationship("User",
                              secondary=project_assistant_user_table,
                              backref="projects_as_assistant", cascade="save-update, merge, delete")
    last_update = Column(DateTime, nullable=False)
    last_action = Column(DateTime, nullable=True)
    tasks = relationship("Task", backref=backref("project"))


    @property
    def city(self):
        return self.location.split("/")[1] if len(self.location.split("/")) > 1 else self.location

    def __repr__(self):
        return "Project('%s', token='%s', template_id='%s', '%s', " \
               "'%s', '%s', '%s', title='%s', " \
               "deadline='%s', promo='%s')" % (self.id, self.token, self.template_id, self.scolaryear,
                                               self.module_title, self.instance_code, self.location, self.title,
                                               dump_datetime(self.deadline, split=False), self.promo)

    @property
    def serialize(self):
        return {
            "id": self.id,
            "token": self.token,
            "template_id": self.template_id,
            "template": self.template.serialize,
            "scolaryear": self.scolaryear,
            "module_title": self.module_title,
            "module_code": self.module_code,
            "instance_code": self.instance_code,
            "location": self.location,
            "city": self.city,
            "title": self.title,
            "deadline": dump_datetime(self.deadline, split=False),
            "promo": self.promo,
            "groups": json.loads(self.groups) if self.groups else None,
            "students": [s.serialize for s in self.students],
            "resp": [u.serialize for u in self.resp],
            "template_resp": [u.serialize for u in self.template_resp],
            "assistants": [u.serialize for u in self.assistants],
            "last_update": dump_datetime(self.last_update, split=False),
            "last_action": dump_datetime(self.last_action, split=False),
            "tasks": [t.serialize_lazy for t in self.tasks]
        }

class Task(Base):
    __tablename__ = 'task'
    id = Column(Integer, primary_key=True)
    type = Column(Enum("auto", "preliminary", "manual"), default="auto")
    launch_date = Column(DateTime, nullable=False)
    status = Column(Enum("ongoing", "todo", "succeed", "failed"), default="todo")
    project_id = Column(Integer, ForeignKey("project.id"))
    exec_cmd = Column(String(200), nullable=True) # override default exec_command
    extend = Column(Text, nullable=True) # json packed extended properties

    def __repr__(self):
        return "<Task id='%s', type='%s', launch_date='%s', status='%s', project_id='%s', project='%s', exec_cmd='%s', " \
               "extend='%s'>" % (self.id, self.type, dump_datetime(self.launch_date, split=False), self.status,
                                 self.project_id, self.project, self.exec_cmd, self.extend)

    @property
    def serialize(self):
        return self._serialize(with_project=True)

    @property
    def serialize_lazy(self):
        return self._serialize(with_project=False)

    def _serialize(self, with_project):
        o = {
            "id": self.id,
            "type": self.type,
            "launch_date": dump_datetime(self.launch_date, split=False),
            "status": self.status,
            "project_id": self.project_id,
            "exec_cmd": self.exec_cmd,
            "extend": json.loads(self.extend) if self.extend else None
        }
        if with_project:
            o["project"] = self.project.serialize
        return o

"""
>>> import models
>>> from models import Task
>>> from config import SQL_DB_URI
>>> from sqlalchemy import create_engine
>>> engine = create_engine(SQL_DB_URI, echo=True)
>>> from sqlalchemy.orm import sessionmaker
>>> Session = sessionmaker()
>>> Session.configure(bind=engine)
>>> session = Session()
>>> session.query(Task).get(1)
"""


if __name__ == "__main__":
    from sqlalchemy import create_engine
    engine = create_engine(SQL_DB_URI, echo=True)
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker()
    Session.configure(bind=engine)

    if len(sys.argv) > 1:
        if sys.argv[1] == "init":
            #en = create_engine(SQL_URI, echo=True)
            #conn = en.connect()
            #conn.execute("commit")
            #conn.execute('drop database if exists ramassage')
            #conn.execute("create database ramassage")
            #conn.close()

            Base.metadata.create_all(engine)
            sys.exit(0)
        if sys.argv[1] == "test_create":
            session = Session()
            ed_user = User(firstname="Steven", lastname="MARTINS", login="martin_6")

            session.add(ed_user)

            template = Template(
                codemodule="B-CUI-150",
                slug="pepito",
                repository_name="pepito",
                call_moulitriche=True,
                call_judge=False,
                school="epitech"
            )

            session.add(template)

            students = [
                User(firstname="Maxime", lastname="D", login="dufres_m"),
                User(firstname="Louis", lastname="K", login="kreher_l"),
                User(firstname="Loïc", lastname="H", login="hidou_l"),
                User(firstname="Jean", lastname="L", login="lemarq_j"),
            ]

            for stud in students:
                session.add(stud)

            resp = [
                ed_user
            ]

            template_resp = [
                User(firstname="Pierre-Jean", lastname="LEGER", login="leger_i")
            ]

            assistants = [
                User(firstname="Victorien", lastname="RAMAGET", login="ramage_v"),
                User(firstname="Nathan", lastname="JANEZCO", login="janecz_n")
            ]

            project = Project(
                token="1f6d77c4-0668-093b-b29e-6a20cb283b4d",
                template=template,
                scolaryear=2014,
                module_title="B2 - Security - beginners",
                module_code="B-CUI-150",
                instance_code="NCY-2-1",
                location="FR/NCY",
                title="Pepito",
                deadline=datetime.datetime.strptime("2015-04-19 23:42:00", "%Y-%m-%d %H:%M:%S"),
                promo=2019,
                groups=json.dumps({}),
                resp=resp,
                template_resp=template_resp,
                last_update=datetime.datetime.now(),
            )
            project.assistants = assistants
            for stud in students:
                project.students.append(Project_Student(user=stud,
                                                        project=project,
                                                        ))

            session.add(ed_user)
            session.add(project)

            session.add(Task(type="auto", launch_date=project.deadline, project=project))
            session.add(Task(type="preliminary", launch_date=project.deadline - datetime.timedelta(days=1), project=project))

            session.commit()
        if sys.argv[1] == "test_update":
            session = Session()
            our_user = session.query(User).filter_by(login='mart_s').first()
            our_user.firstname = "Steven1"
            session.commit()

        if sys.argv[1] == "test_read":
            session = Session()
            #ed_user = Student(firstname="Steven", lastname="MARTINS", login="martin_6")
            #session.add(ed_user)
            our_user = session.query(User).filter_by(firstname='Steven').first()
            #session.commit()
