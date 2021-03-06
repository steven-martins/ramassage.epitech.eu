#!/usr/bin/env python3
__author__ = 'Steven'

try:
    import httplib
except:
    import http.client as httplib

try:
    from ConfigParser import ConfigParser, Error, NoOptionError
except:
    from configparser import ConfigParser, Error, NoOptionError

from optparse import OptionParser, OptionValueError
import inspect
import json
import time
import hashlib
import hmac
import base64
import os
import uuid
import pytz
import urllib
import datetime
import sys
import csv
import logging

VERSION = "0.1 beta"

class Conf:
    def __init__(self, filename):
        self._filename = filename
        try:
            self._config = ConfigParser(strict=False)
        except:
            self._config = ConfigParser()
        try:
            self._config.read(os.path.expanduser(filename))
        except Exception as e:
            logging.error("[Conf]" + self._filename + ": " + str(e))
            raise Exception("Error during loading file " + self._filename)

    def getSection(self, section):
        data={}
        try:
            if section in self._config.sections():
                for name, value in self._config.items(section):
                    data[name] = value
        except Exception as e:
            logging.error("[Conf]" + self._filename + ": " + str(e))
        for key, value in data.items():
            if ", " in value:
                data[key] = value.split(", ")
        return data

    def get(self, section, option, default=""):
        val = default
        try:
            val = self._config.get(section, option)
        except:
            val = default
        if ", " in val:
            return val.split(", ")
        return default

    def sections(self):
        return self._config.sections()

    def setSection(self, section, values):
        if not self._config.has_section(section):
            self._config.add_section(section)
        for k, v in values.items():
            self._config.set(section, k, v)

    def setValue(self, section, option, value):
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, option, value)

    def removeSection(self, section):
        if self._config.has_section(section):
            self._config.remove_section(section)

    def removeValue(self, section, option):
        if self._config.has_section(section) and self._config.has_option(section, option):
            self._config.remove_option(section, option)

    def save(self):
        with open(self._filename, 'w') as f:
            self._config.write(f)

    def getAll(self):
        data = {}
        for section in self.sections():
            data[section] = self.getSection(section)
        return data

class Controller(object):
    def __init__(self):
        self._options = {}
        self._config = {}

        config = Conf(os.path.expanduser(".atomrc" if os.path.exists(".atomrc") else "~/.atomrc")).getSection("credentials")
        self._config["URI"] = os.getenv("URI", "api.ramassage.epitech.eu" if "uri" not in config else config["uri"])
        self._config["UUID"] = os.getenv("UUID", config["uuid"] if "uuid" in config else None)
        self._config["HASH"] = os.getenv("HASH", config["hash"] if "hash" in config else None)
        if "UUID" not in self._config or self._config["UUID"] == None or "HASH" not in self._config or self._config["HASH"] == None:
            print("ERROR: Credentials are missing", file=sys.stderr)
            sys.exit(1)

    def _sign(self, d, method, url, datas=None):
        if method == "POST":
            data = datas.decode("utf-8") if datas else ""
        else:
            data = url
        hm = hmac.new(self._config["HASH"].encode("utf-8"), "{0}-{1}".format(str(int(time.mktime(d.timetuple()))),
            data).encode("utf-8"), hashlib.sha256)

        l = hm.hexdigest() if not self._config["UUID"] else "%s:%s" % (self._config["UUID"], hm.hexdigest())
        return "Sign %s" % base64.b64encode(l.encode("utf-8")).decode("utf-8")

    def _storeFile(self, url, response):
        dir = "."
        url = os.path.join(dir, str(uuid.uuid4()) + ".zip")
        with open(url, 'wb') as f:
            f.write(response.read(65 * 1024))
        return {"file": url}

    def _req(self, method, url, datas=None, data_type="application/json"):
        conn = httplib.HTTPConnection(self._config["URI"])
        headers = {"Content-type": "application/json"}
        d = datetime.datetime.now(pytz.timezone('Europe/Paris'))
        headers["Date"] = d.strftime('%a, %d %b %Y %H:%M:%S %z')
        headers["Authorization"] = self._sign(d, method, url,
                                              json.dumps(datas).encode("utf-8") if data_type == "application/json"
                                              else datas.encode("utf-8"))
        if data_type == "application/json":
            conn.request(method, url, urllib.parse.urlencode(datas) if datas and method == "GET" else json.dumps(datas).encode("utf-8"), headers=headers)
        else:
            conn.request(method, url, urllib.parse.urlencode(datas) if datas and method == "GET" else datas.encode("utf-8"), headers=headers)
        #conn.set_debuglevel(1)
        response = conn.getresponse()
        content_type = response.getheader("Content-Type")
        if response.status > 201:
            print('%s: %s %s' % (url, response.status, response.reason))
        try:
            if content_type.find("zip") >= 0:
                return self._storeFile(url, response)
            return json.loads(response.read().decode())
        except Exception as e:
            print("get Exception: %s" % e)
            return {}

    def _get(self, url):
        return self._req("GET", url)

    def _post(self, url, datas):
        return self._req("POST", url, datas)

    def _delete(self, url):
        return self._req("DELETE", url)

    def _upload(self, url, f, form="PUT"):
        import requests
        print(os.path.basename(f))
        headers = {}
        res = requests.put("http://" + self._machine + url, files={"file": (os.path.basename(f), open(f, 'rb'))},
                           headers=headers)
        print(res.text)

    def _post_notes(self, url, filename):
        raw_datas = ""
        with open(filename, "r") as f:
            raw_datas = f.readlines()
        print(raw_datas)
        return self._req("POST", url, "".join(raw_datas), "text/csv")

    def searchAction(self, slug, *args):
        """Find project(s) by slug"""
        res = self._get("/1.0/project/slug/%s" % slug)
        projects = sorted(res["projects"], key=lambda k: k["city"], reverse=False)
        print("%s project(s) found:\n" % len(projects))
        city = self._options.city
        for p in projects:
            if not city or city == p["city"]:
                #if self._confirm("Displaying %s" % city):
                print(self._beautify_project(p))
        return True

    def _write_csv(self, file_name, rows, directory="."):
        with open(os.path.join(directory, file_name), 'w') as f:
            writer = csv.writer(f, delimiter=';', quoting=csv.QUOTE_NONE, lineterminator='\n')
            writer.writerows(rows)

    def loginsAction(self, slug, filename, type="simple"):
        """ Generate a file containing logins of project(s) corresponding to the slug
                (type: simple or full)
        """
        res = self._get("/1.0/project/slug/%s" % slug)
        projects = sorted(res["projects"], key=lambda k: k["city"], reverse=False)
        city = self._options.city
        l = []
        for p in projects:
            if not city or city == p["city"]:
                for stud in p["students"]:
                    l.append([stud["user"]["login"]] if type == "simple" else [stud["user"]["login"], p["city"], stud["user"]["firstname"],
                                 stud["user"]["lastname"]])
        self._write_csv(filename, l)
        return True

    def projectAction(self, uid, *args):
        """Show project information"""
        res = self._get("/1.0/project/%s" % uid)
        print(res)
        print(self._beautify_project(res))
        return True

    def moulitricheAction(self, slug, *args):
        """Call moulitriche for the specified slug"""
        res = self._get("/1.0/project/slug/%s/moulitriche" % slug)
        print(res)
        return True

    def statsAction(self, slug):
        """Display pickup's statistics"""
        res = self._get("/1.0/project/slug/%s" % slug)
        projects = sorted(res["projects"], key=lambda k: k["city"], reverse=False)
        for p in projects:
            if not self._options.city or self._options.city == p["city"]:
                #if self._confirm("Displaying %s" % city):
                print("%s: " % p["city"])
                for s in p["students"]:
                    print("%s: %s - %s" % (s["user"]["login"], s["status"], s["logs"]))
                print("")
        return True

    def pushAction(self, slug, filename):
        """Push notes"""
        res = self._get("/1.0/project/slug/%s" % slug)
        projects = sorted(res["projects"], key=lambda k: k["city"], reverse=False)
        for p in projects:
            if not self._options.city or self._options.city == p["city"]:
                if self._confirm(" %s" % p["city"]):
                    self._post_notes("/1.0/project/%s/notes" % (p["id"]), filename)
        return True

    def refreshAction(self, slug):
        """Update local data from intranet"""
        res = self._get("/1.0/project/slug/%s" % slug)
        projects = sorted(res["projects"], key=lambda k: k["city"], reverse=False)
        for p in projects:
            if not self._options.city or self._options.city == p["city"]:
                if self._confirm(" %s" % p["city"]):
                    self._get("/1.0/project/%s/refresh" % (p["id"]))
        return True

    def judgeAction(self, slug, _type="manual"):
        """Judging a specified project"""
        res = self._get("/1.0/project/slug/%s" % slug)
        projects = sorted(res["projects"], key=lambda k: k["city"], reverse=False)
        for p in projects:
            if not self._options.city or self._options.city == p["city"]:
                if self._confirm(" %s" % p["city"]):
                    self._post("/1.0/project/%s/judge" % (p["id"]), {"id": p["id"], "kind": _type})
        return True

    def pickupAction(self, slug, date=None):
        """Schedule a pickup"""
        _date = datetime.datetime.now()
        if date:
            #parsedatetime ?
            _date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        res = self._get("/1.0/project/slug/%s" % slug)
        projects = sorted(res["projects"], key=lambda k: k["city"], reverse=False)
        print("%s project(s) found:\n" % len(projects))
        if len(projects) == 0:
            return False
        for p in projects:
            if not self._options.city or self._options.city == p["city"]:
                print(self._beautify_project(p))
                if self._confirm("Picking up %s %s." % (p["city"], "Now" if not date else "at %s" % _date.strftime("%Y-%m-%d %H:%M:%S"))):
                    self._post("/1.0/task/", {"type": "manual", "launch_date": _date.strftime('%Y-%m-%d %H:%M:%S'),
                                             "status": "todo", "project_id": p["id"], "exec_cmd": "", "extend": "{}"})
        return True

    def _beautify_project(self, obj):
        for k, v in obj["template"].items():
            obj["template.%s" % k] = v
        obj["assistants_join"] = ", ".join(["%s %s" % (u["firstname"], u["lastname"]) for u in obj["assistants"]])
        obj["responsables_join"] = ", ".join(["%s %s" % (u["firstname"], u["lastname"]) for u in obj["resp"]])
        obj["templates_resp_join"] = ", ".join(["%s %s" % (u["firstname"],
                                                           u["lastname"]) for u in obj["template_resp"]])
        students = obj["students"]
        nb_succeed = 0
        for s in students:
            if s["status"] == "Succeed":
                nb_succeed += 1
        obj["stats_students"] = "%s (%.2f%%, %s/%s picked up)" % (len(students), (nb_succeed / len(students)) * 100,
                                                                 nb_succeed, len(students)) \
            if nb_succeed > 0 else "%s" % (len(students))
        obj["pickups"] = ", ".join(["%s (%s)" % (t["launch_date"], t["status"]) for t in
                                    sorted(obj["tasks"],
                                           key=lambda t: datetime.datetime.strptime(t["launch_date"],
                                                                                    "%Y-%m-%d %H:%M:%S"))])
        #obj.update(obj["template"] if "template" in obj else {})
        # - Template resp: %(templates_resp_join)s
        return """%(title)s - %(city)s (#%(id)s) :
    - Scolaryear: %(scolaryear)s
    - City: %(city)s
    - Deadline: %(deadline)s
    - Module: %(module_title)s (%(module_code)s)
    - Instance: %(instance_code)s
    - Slug: %(template.slug)s
    - Repository: %(template.repository_name)s
    - Assistants: %(assistants_join)s
    - Resp: %(responsables_join)s
    - Students stats: %(stats_students)s
    - Pickup(s) : %(pickups)s
""" % (obj)

    """
        Actions interessantes :
            o uploader des notes : soit avec un slug +/- ville(s), soit avec l'id
            o stats sur un ramassage (slug + ville, ou id)
            o recuperer adresses emails pour un projet
            o infos sur un template
            o infos sur un module ?
            o recuperer les projets d'un utilisateur
    """

    @property
    def usage(self):
        ret = "usage: %prog [options] command [params...]\n"
        ret += "Credentials (UUID and HASH) need to be stored in environment or in a file ~/.atomrc\n"
        ret += "Example:\n"
        ret += "[credentials]\n"
        ret += "UUID=...\n"
        ret += "HASH=...\n\n"
        ret += "Command(s) available:\n"
        for function_name, fn in inspect.getmembers(self.__class__, predicate=inspect.isfunction):
            #print("function_name(%s) : fn(%s)" % (function_name, fn))
            if function_name.endswith("Action"):
                ret += "\to %s [%s]\n\t\t%s\n" % (function_name.replace("Action", ""),
                                                ", ".join(inspect.getargspec(fn).args[1:]),
                                                fn.__doc__ if fn.__doc__ else "")
        return ret

    def _execute(self, args):
        cmd = args[0]
        method = "%sAction" % (cmd.lower())
        try:
            for function_name, fn in inspect.getmembers(self.__class__, predicate=inspect.isfunction):
                if method == function_name:
                    result = fn(self, *args[1:])
                    if result == False:
                        sys.exit(1)
                    return True
        except Exception as e:
            print(str(e))
            return True
        sys.stderr.write("%s: Command not found\n\n" % cmd)
        return False

    def _confirm(self, question=None):
        if self._options.yes:
            return True
        if question:
            print(question)
        flag = True
        while flag:
            msg = input("Do you confirm this action (yes/no) ? ")
            if msg == "yes" or msg == "y":
                return True
            if msg == "no" or msg == "n":
                return False
        return False

    def execute(self):
        def option_city(option, opt_str, value, parser):
            if value not in ("BDX", "LIL", "LYN", "MAR", "MPL", "NAN",
                             "NCE", "NCY", "PAR", "REN", "STG", "TLS"):
                raise OptionValueError("Unknown city: %s" % value)
            setattr(parser.values, option.dest, value)

        parser = OptionParser(self.usage, version=VERSION)
        parser.add_option("-c", "--config", dest="filename",
                          help="using a specific config file FILE", metavar="FILE")
        parser.add_option("-j", "--json",
                          action="store_true", dest="json",
                          help="display output as json", default=False)
        parser.add_option("-y", "--yes",
                          action="store_true", dest="yes",
                          help="Assume Yes to all queries and do not prompt", default=False)
        parser.add_option("-q", "--quiet",
                          action="store_false", dest="verbose", default=True,
                          help="don't print status messages to stdout")
        parser.add_option("-C", "--city", dest="city", action="callback",
                          type="str", nargs=1,
                          help="restrict actions to a specific city", default=None,
                          callback=option_city)

        (self._options, args) = parser.parse_args()
        if len(args) == 0:
            return parser.print_usage()
        #print("options: %s" % str(self._options))
        #print("args: %s" % str(args))
        if not self._execute(args):
            sys.stderr.write(parser.get_usage())


if __name__ == "__main__":
    Controller().execute()
