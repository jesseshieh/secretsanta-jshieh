#!/usr/bin/env python
# author: Jesse Shieh (jesse.shieh@gmail.com)

import os
import random
import re
import time
import urllib
import wsgiref.handlers
from google.appengine.api import mail
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

debug_mode = True

class Invitee(db.Model):
  email = db.EmailProperty(required=True)
  name = db.StringProperty()

class Game(db.Model):
  creator = db.ReferenceProperty(Invitee, required=True)
  invitees = db.ListProperty(db.Key) # list of Invitees

class BaseHandler(webapp.RequestHandler):
  template_values = {
    "title": "Secret Santa",
    }

  # append text to the debug log in the HTML output
  def log(self, msg):
    if debug_mode:
      msg += "<br>"
      try:
        self.template_values["debug_log"] = \
          self.template_values["debug_log"] + msg
      except KeyError:
        self.add_template_value("debug_log", msg)

  # adds a new entry in the template dictionary
  def add_template_value(self, key, value):
    self.template_values[key] = value

  # special case of add_template_value that pulls the value from the
  # request object (it's a url parameter of the same name)
  def add_template_value_from_request(self, key):
    self.add_template_value(key, self.request.get(key))

  # renders and writes the response given the template name
  def render(self, template_name):
    path = os.path.join(os.path.dirname(__file__), template_name)
    self.response.out.write(template.render(path, self.template_values))

  # translate the array cycle into a dictionary (could be useful)
  # TODO(jesses): consider putting this in a more appropriate class
  def create_assignment_dictionary(self, list):
    assignments = {}
    for i in range(len(list) - 1):
      assignments[list[i]] = list[i + 1]
    assignments[list[-1]] = list[0]
    return assignments

class MainHandler(BaseHandler):
  def get(self):
    self.render("main.html")

class ManageHandler(BaseHandler):
  def get(self):
    code = self.request.get("code")
    if code == '':
      self.response.out.write("Missing code")
      return

    game = db.get(db.Key(code))

    invitee_objs = []
    for key in game.invitees:
      invitee_objs.append(db.get(key))
    assignments = self.create_assignment_dictionary(invitee_objs)

    self.add_template_value("assignments", assignments)
    self.add_template_value("creator", str(game.creator.key()))

    self.render("manage.html")

class EmailHandler(BaseHandler):
  def get(self):
    code = self.request.get("code")
    if code != '':
      game = db.get(db.Key(code))
      creator = game.creator.key()
      assignments = self.create_assignment_dictionary(game.invitees)
      for key in assignments.keys():
        value = assignments[key]
        giver = str(key)
        receiver = str(value)
        urllib.quote(giver) # urlescape
        urllib.quote(receiver)

        task = Task(url='/tasks/email', params={
            'giver': giver,
            'receiver': receiver,
            'creator': creator})
        task.add('email-throttle')
    else:
      giver = self.request.get("giver")
      receiver = self.request.get("receiver")
      creator = self.request.get("creator")

      urllib.quote(giver) # urlescape
      urllib.quote(receiver)
      urllib.quote(creator)

      task = Task(url='/tasks/email', params={
          'giver': giver,
          'receiver': receiver,
          'creator': creator})
      task.add('email-throttle')

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class EmailWorker(BaseHandler):
  def post(self):
    is_creator_email = (self.request.get('is_creator_email',
                                         'False') == "True")
    if is_creator_email:
      creator = self.request.get('creator')
      code = self.request.get('code')
      urllib.unquote(creator)
      urllib.unquote(code)
      creator_obj = db.get(db.Key(creator))
      self.add_template_value("creator",
                              creator_obj.name
                              + " ("
                              + creator_obj.email
                              + ")")
      self.add_template_value("code", code)

      # send mail to creator using same template_values
      html_body = template.render(os.path.join(os.path.dirname(__file__),
                                               "confirm_email.html"),
                                  self.template_values)
      mail.send_mail(sender=creator_obj.email,
                     to=creator_obj.email,
                     subject="Your Secret Santa Gift Exchange",
                     body=html_body,
                     html=html_body)
    else:
      giver_key = self.request.get('giver')
      receiver_key = self.request.get('receiver')
      creator_key = self.request.get('creator')
      urllib.unquote(giver_key)
      urllib.unquote(receiver_key)
      urllib.unquote(creator_key)

      giver_obj = db.get(db.Key(giver_key))
      receiver_obj = db.get(db.Key(receiver_key))
      creator_obj = db.get(db.Key(creator_key))
      giver = giver_obj.name + " (" + giver_obj.email + ")"
      receiver = receiver_obj.name + " (" + receiver_obj.email + ")"

      # send mail to invitee
      self.add_template_value("giver", giver)
      self.add_template_value("receiver", receiver)
      html_body = template.render(os.path.join(os.path.dirname(__file__),
                                               "invitee_email.html"),
                                  self.template_values)
      mail.send_mail(sender=creator_obj.email,
                     to=giver_obj.email,
                     subject="Your Secret Santa Assignment",
                     body=html_body,
                     html=html_body)


class ConfirmHandler(BaseHandler):
  # randomize an array
  def randomize(self, dict):
    # convert to list
    list = []
    for k,v in dict.iteritems():
      list.append(v)

    length = len(list)
    for i in range(length):
      j = random.randrange(i, length)
      list[i], list[j] = list[j], list[i]

    return list

  def post(self):
    creator_email = self.request.get("creator_email")
    creator_name = self.request.get("creator_name")
    creator = Invitee(email=creator_email,
                      name=creator_name)

    is_creator_participating = (self.request.get("is_creator_participating",
                                                "True") == "True")

    # array of invitees (don't forget to add the creator)
    invitees = {}
    if is_creator_participating:
      invitees[0] = creator
    else:
      # normally, it would get "put" along with the invitees, now it doesn't
      # so we must do it as a one-off
      creator.put()

    # invitee post parameter regular expression
    invitee_email_re = re.compile(r"invitee(\d+)_email")
    invitee_name_re = re.compile(r"invitee(\d+)_name")

    # iterate through args
    for key in self.request.arguments():
      # if this is an invitee, then add it to the invitee array
      email_match = invitee_email_re.match(key)
      name_match = invitee_name_re.match(key)
      if email_match:
        id = email_match.group(1)
      elif name_match:
        id = name_match.group(1)
      else:
        continue # skip the rest

      value = self.request.get(key)
      if len(value) == 0:
        continue

      try:
        invitee = invitees[id]
        # entry exists, move on
      except KeyError:
        # entry missing, create
        invitee = Invitee(email="required", name="")
        invitees[id] = invitee

      if email_match:
        invitees[id].email = value
      if name_match:
        invitees[id].name = value

    # randomize the order of invitees
    invitees = self.randomize(invitees)

    invitee_keys = []
    for invitee in invitees:
      invitee.put()
      invitee_keys.append(invitee.key())


    # insert game into datastore
    game = Game(creator=creator,
                invitees=invitee_keys)
    game.put()

    # sent creator email through email-throttle queue
    creator_key = str(creator.key())
    code = str(game.key())
    urllib.quote(creator_key)
    urllib.quote(code)
    task = Task(url='/tasks/email', params={
        'is_creator_email': 'True',
        'creator': creator_key,
        'code': code})
    task.add('email-throttle')

    # render
    assignments = self.create_assignment_dictionary(invitees)
    self.add_template_value("assignments", assignments)
    self.add_template_value("code", code)
    self.render("confirm.html")

def main():
  # boilerplate application registration stuff
  application = webapp.WSGIApplication([("/", MainHandler),
                                        ("/email", EmailHandler),
                                        ("/confirm", ConfirmHandler),
                                        ("/manage", ManageHandler),
                                        ("/tasks/email", EmailWorker)],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()
