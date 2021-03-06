__author__ = 'steven'

from flask import Blueprint, jsonify, request, send_from_directory
from sqlalchemy.exc import IntegrityError
from models import Project, Project_Student, Template, Task, User
import logging
import json
from datetime import datetime

project = Blueprint('project', __name__)

from api_tools import signed_auth, nocache, cached


@project.route('/', methods=["GET"])
@signed_auth()
@nocache
def api_get_projects():
    from api import db, api_return_error
    try:
        projects = db.session.query(Project).filter(Project.deadline>=datetime.now()).all()
    except Exception as e:
        return api_return_error(500, "Server error", str(e))
    return jsonify({"projects": [p.serialize for p in projects]}), 200


@project.route('/past', methods=["GET"])
@signed_auth()
@nocache
def api_get_projects_past():
    from api import db, api_return_error
    try:
        projects = db.session.query(Project).filter(Project.deadline<datetime.now()).all()
    except Exception as e:
        return api_return_error(500, "Server error", str(e))
    return jsonify({"projects": [p.serialize for p in projects]}), 200

@project.route('/all', methods=["GET"])
@signed_auth()
@nocache
def api_get_projects_all():
    from api import db, api_return_error
    try:
        projects = db.session.query(Project).all()
    except Exception as e:
        return api_return_error(500, "Server error", str(e))
    return jsonify({"projects": [p.serialize for p in projects]}), 200



@project.route('/', methods=["POST"])
@signed_auth()
def api_post_project():
    # module_code, slug, token, scolaryear,
    # module_title, module_code, instance_code,
    # location, title, deadline, promo
    # groups, students, resp, template_resp, assistants
    from api import db, api_return_error
    try:
        datas = request.json

        tpl = db.session.query(Template).filter_by(codemodule=datas["module_code"], slug=datas["slug"]).first()
        if not tpl:
            tpl = Template(codemodule=datas["module_code"], slug=datas["slug"])
            # repository_name, call*, school, ...
            db.session.add(tpl)
        t = Project(template=tpl,
                    token=datas["token"],
                    scolaryear=datas["scolaryear"],
                    module_title=datas["module_title"],
                    module_code=datas["module_code"],
                    instance_code=datas["instance_code"],
                    location=datas["location"],
                    title=datas["title"],
                    deadline=datetime.strptime(datas["deadline"], "%Y-%m-%d %H:%M:%S"),
                    promo=datas["promo"],
                    last_update=datetime.now(),
                    groups=json.dumps(datas["groups"]))
        resp = []
        for user in datas["resp"]:
            u = db.session.query(User).filter_by(login=user["login"]).first()
            if not u:
                u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                db.session.add(u)
            resp.append(u)
        t.resp = resp
        template_resp = []
        for user in datas["template_resp"]:
            u = db.session.query(User).filter_by(login=user["login"]).first()
            if not u:
                u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                db.session.add(u)
            template_resp.append(u)
        t.template_resp = template_resp
        assistants = []
        for user in datas["assistants"]:
            u = db.session.query(User).filter_by(login=user["login"]).first()
            if not u:
                u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                db.session.add(u)
            assistants.append(u)
        t.assistants = assistants

        for user in datas["students"]:
            u = db.session.query(User).filter_by(login=user["login"]).first()
            if not u:
                u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                db.session.add(u)
            t.students.append(Project_Student(user=u, project=t))

        db.session.add(t)
        db.session.add(Task(type="auto", launch_date=t.deadline, project=t))
        #db.session.add(Task(type="preliminary", launch_date=project.deadline - datetime.timedelta(days=1), project=project))
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        return api_return_error(409, "Conflict", str(e))
    except KeyError as e:
        return api_return_error(400, "Bad Request", "Field %s is missing" % str(e))
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify(t.serialize), 201


@project.route('/<int:_id>', methods=["GET"])
@signed_auth()
@nocache
def api_get_project(_id):
    from api import db, api_return_error
    try:
        p = db.session.query(Project).get(_id)
        if not p:
            return api_return_error(404, "Project #%s not found" % _id)
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify(p.serialize), 200


@project.route('/<int:_id>/refresh', methods=["GET"])
@signed_auth()
@nocache
def api_get_project_refresh(_id):
    from api import db, api_return_error
    from tasks import fetch
    try:
        p = db.session.query(Project).get(_id)
        if not p:
            return api_return_error(404, "Project #%s not found" % _id)
        fetch.delay(p.token, 0)
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify(p.serialize), 200


@project.route('/token/<string:token>', methods=["GET"])
@project.route('/<string:token>', methods=["GET"])
@signed_auth()
@nocache
def api_get_project_token(token):
    from api import db, api_return_error
    try:
        p = db.session.query(Project).filter_by(token=token).first()
        if not p:
            return api_return_error(404, "Project #%s not found" % token)
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify(p.serialize), 200


@project.route('/<int:_id>/delivery/last', methods=["GET"])
@signed_auth()
@cached(max_age=0, must_revalidate=True)
def api_get_project_delivery_last(_id):
    from api import db, api_return_error
    from actions.send import SendFile
    from exceptions import FileMissing
    try:
        p = db.session.query(Project).get(_id)
        if not p:
            return api_return_error(404, "Project #%s not found" % _id)
        s = SendFile(p.serialize)
        return send_from_directory(*s.path())
    except FileMissing as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(404, str(e))
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return api_return_error(400, "Bad request")

#/delivery/last
#/delivery/official


@project.route('/slug/<string:slug>', methods=["GET"])
@signed_auth()
@nocache
def api_get_project_slug(slug):
    from api import db, api_return_error
    try:
        projects = db.session.query(Project).join(Project.template).filter(Template.slug==slug).all()
        if not projects:
            return api_return_error(404, "Slug %s not found" % slug)
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify({"projects": [p.serialize for p in projects]}), 200

@project.route('/slug/<string:slug>/moulitriche', methods=["GET"])
@signed_auth()
@nocache
def api_get_project_slug_moulitriche(slug):
    from api import db, api_return_error
    from actions.inform import InformTriche
    result = False
    try:
        project = db.session.query(Project).join(Project.template).filter(Template.slug==slug).first()
        if not project:
            return api_return_error(404, "Slug %s not found" % slug)
        result = InformTriche(project.serialize).result
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify({"status": result}), 200


@project.route('/template/<int:_id>', methods=["GET"])
@signed_auth()
@nocache
def api_get_project_by_template(_id):
    from api import db, api_return_error
    try:
        projects = db.session.query(Project).join(Project.template).filter(Template.id==_id).all()
        if not projects:
            return api_return_error(404, "Template #%s not found" % _id)
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify({"projects": [p.serialize for p in projects]}), 200

@project.route('/user/<string:login>', methods=["GET"])
@signed_auth()
@nocache
def api_get_project_current_student(login):
    from api import db, api_return_error
    try:
        # Si chef de groupe uniquement :
        #projects = db.session.query(Project).join(Project_Student, Project_Student.project_id == Project.id)\
        #    .join(User, User.id == Project_Student.user_id).filter(User.login==login)\
        #    .filter(Project.deadline>=datetime.now()).all()
        projects = db.session.query(Project).join(Project_Student, Project_Student.project_id == Project.id)\
            .join(User, User.id == Project_Student.user_id).filter(Project.groups.like('%{0}%'.format(login)))\
            .filter(Project.deadline>=datetime.now()).all()
        if not projects:
            return api_return_error(404, "User %s not found" % login)
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify({"projects": [p.serialize for p in projects]}), 200

@project.route('/all/user/<string:login>', methods=["GET"])
@signed_auth()
@nocache
def api_get_project_all_student(login):
    from api import db, api_return_error
    try:
        # Si chef de groupe uniquement :
        #projects = db.session.query(Project).join(Project_Student, Project_Student.project_id == Project.id)\
        #    .join(User, User.id == Project_Student.user_id).filter(User.login==login).all()
        projects = db.session.query(Project).join(Project_Student, Project_Student.project_id == Project.id)\
            .join(User, User.id == Project_Student.user_id).filter(Project.groups.like('%{0}%'.format(login))).all()
        if not projects:
            return api_return_error(404, "User %s not found" % login)
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify({"projects": [p.serialize for p in projects]}), 200


@project.route('/<int:_id>', methods=["PUT"])
@signed_auth()
def api_put_project(_id):
    from api import db, api_return_error
    try:
        datas = request.json

        t = db.session.query(Project).get(_id)

        t.token = datas["token"]
        t.scolaryear = datas["scolaryear"]
        t.module_title = datas["module_title"]
        t.module_code = datas["module_code"]
        t.instance_code = datas["instance_code"]
        t.location = datas["location"]
        t.title = datas["title"]
        t.deadline = datetime.strptime(datas["deadline"], "%Y-%m-%d %H:%M:%S")
        t.promo = datas["promo"]
        t.groups = json.dumps(datas["groups"])
        t.last_update = datetime.now()
        resp = []
        for user in datas["resp"]:
            u = db.session.query(User).filter_by(login=user["login"]).first()
            if not u:
                u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                db.session.add(u)
            resp.append(u)
        t.resp = resp
        template_resp = []
        for user in datas["template_resp"]:
            u = db.session.query(User).filter_by(login=user["login"]).first()
            if not u:
                u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                db.session.add(u)
            template_resp.append(u)
        t.template_resp = template_resp
        assistants = []
        for user in datas["assistants"]:
            u = db.session.query(User).filter_by(login=user["login"]).first()
            if not u:
                u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                db.session.add(u)
            assistants.append(u)
        t.assistants = assistants
        t.students = []
        for user in datas["students"]:
            u = db.session.query(User).filter_by(login=user["login"]).first()
            if not u:
                u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                db.session.add(u)
            t.students.append(Project_Student(user=u, project=t))

        db.session.add(t)
        for task in t.tasks:
            if task.type == "auto":
                task.launch_date = t.deadline
                db.session.add(task)
        #db.session.add(Task(type="preliminary", launch_date=project.deadline - datetime.timedelta(days=1), project=project))
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        return api_return_error(409, "Conflict", str(e))
    except KeyError as e:
        return api_return_error(400, "Bad Request", "Field %s is missing" % str(e))
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify(t.serialize), 200


@project.route('/<int:_id>', methods=["PATCH"])
@signed_auth()
def api_patch_project(_id):
    from api import db, api_return_error
    try:
        datas = request.json

        t = db.session.query(Project).get(_id)

        for k, v in datas.items():
            if k in ("token", "scolaryear", "module_title", "instance_code", "location",
                     "title", "promo"):
                setattr(t, k, v)

        #"module_code", "slug", deadline, groups
        if ("module_code" in datas and t.module_code != datas["module_code"]) or (
                        "slug" in datas and t.template.slug != datas["slug"]):
            slug = datas["slug"] if "slug" in datas else t.template.slug
            module_code = datas["module_code"] if "module_code" in datas else t.module_code
            tpl = db.session.query(Template).filter_by(codemodule=module_code, slug=slug).first()
            if not tpl:
                tpl = Template(codemodule=module_code, slug=slug)
                db.session.add(tpl)
            t.module_code = module_code
            t.template = tpl
        if "deadline" in datas:
            t.deadline = datetime.strptime(datas["deadline"], "%Y-%m-%d %H:%M:%S")
            for task in t.tasks:
                if task.type == "auto":
                    task.launch_date = t.deadline
                    db.session.add(task)

        if "groups" in datas:
            t.groups = json.dumps(datas["groups"])
        t.last_update = datetime.now()
        if "resp" in datas:
            resp = []
            for user in datas["resp"]:
                u = db.session.query(User).filter_by(login=user["login"]).first()
                if not u:
                    u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                    db.session.add(u)
                resp.append(u)
            t.resp = resp
        if "template_resp" in datas:
            template_resp = []
            for user in datas["template_resp"]:
                u = db.session.query(User).filter_by(login=user["login"]).first()
                if not u:
                    u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                    db.session.add(u)
                template_resp.append(u)
            t.template_resp = template_resp
        if "assistants" in datas:
            assistants = []
            for user in datas["assistants"]:
                u = db.session.query(User).filter_by(login=user["login"]).first()
                if not u:
                    u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                    db.session.add(u)
                assistants.append(u)
            t.assistants = assistants
        if "students" in datas:
            t.students = []
            for user in datas["students"]:
                u = db.session.query(User).filter_by(login=user["login"]).first()
                if not u:
                    u = User(firstname=user["firstname"], lastname=user["lastname"], login=user["login"])
                    db.session.add(u)
                t.students.append(Project_Student(user=u, project=t))

        db.session.add(t)
        #db.session.add(Task(type="preliminary", launch_date=project.deadline - datetime.timedelta(days=1), project=project))
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        return api_return_error(409, "Conflict", str(e))
    except KeyError as e:
        return api_return_error(400, "Bad Request", "Field %s is missing" % str(e))
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify(t.serialize), 200


@project.route('/<int:_id>/judge', methods=["POST"])
@signed_auth()
def api_post_project_judge(_id):
    from api import db, api_return_error
    from tasks import scheduled_judge
    try:
        datas = request.json
        type_of_judging = datas["kind"] if "kind" in datas else "manual"
        p = db.session.query(Project).get(_id)
        if not p:
            return api_return_error(404, "Project #%s not found" % _id)
        for task in p.tasks:
            if task.type == type_of_judging:
                scheduled_judge.delay(task.id)
                return jsonify(task.serialize), 200
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return api_return_error(404, "Task not found")


@project.route('/<int:_id>/notes', methods=["POST"])
@signed_auth()
def api_post_project_notes(_id):
    from api import db, api_return_error
    import io
    import csv
    from mixins.crawl import CrawlerMixin
    rows = {}
    try:
        datas = request.get_data().decode("utf-8")
        try:
            json.loads(datas)
        except:
            f = io.StringIO(datas)
            hdr = []
            reader = csv.reader(f, delimiter=';', quoting=csv.QUOTE_NONE)
            for row in reader:
                line = {}
                if len(hdr) == 0:
                    hdr = row
                else:
                    i = 0
                    for elem in row:
                        line[hdr[i]] = elem
                        i += 1
                    rows[line[hdr[0]]] = line
        t = db.session.query(Project).get(_id)
        if not t:
            return api_return_error(404, "Project %s not found" % _id)
        # expand groups
        login_students = []
        for sp in t.students:
            login_students.append(sp.user.login)
        groups = []
        try:
            groups = json.loads(t.groups)
        except Exception as e:
            return api_return_error(500, "Unable to expand groups")
        for group in groups:
            master = None
            for member in group:
                if member["login"] in rows:
                    master = member["login"]
            if member:
                for member in group:
                    if member["login"] != master:
                        tmp = dict(rows[master])
                        tmp[hdr[0]] = member["login"]
                        rows[member["login"]] = tmp
                        login_students.append(member["login"])
        out = []
        for login in login_students:
            if login in rows:
                out.append(rows[login])
        crawl = CrawlerMixin()
        crawl._post_notes(t.token, out)
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        return api_return_error(409, "Conflict", str(e))
    except KeyError as e:
        return api_return_error(400, "Bad Request", "Field %s is missing" % str(e))
    except Exception as e:
        db.session.rollback()
        logging.error(str(e))
        return api_return_error(500, "Server error", str(e))
    return jsonify({"rows": out}), 200
