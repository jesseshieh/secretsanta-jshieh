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
  email_body = db.StringProperty(multiline=True, default="Thanks for participating in the secret santa gift exchange!  This is an automatically generated personal email.  The person you need to buy a gift for is listed below.  Spend around $20 and we'll exchange gifts next Saturday at 6pm at my place. \
")

class BaseHandler(webapp.RequestHandler):
  template_values = {
    "title": "Secret Santa",
    "theme": "ui-lightness",
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
    self.add_template_value("code", code)
    self.add_template_value("email_body", game.email_body)

    self.render("manage.html")

class EmailHandler(BaseHandler):
  def post(self):
    code = urllib.unquote(self.request.get("code"))

    game = db.get(db.Key(code))
    creator_key = urllib.quote(str(game.creator.key()))
    email_body = urllib.quote(game.email_body)
    assignments = self.create_assignment_dictionary(game.invitees)

    if self.request.get("giver") != '':
      # giver specified, just send to him
      giver_key = self.request.get("giver") # already url escaped
      receiver_key = urllib.quote(str(assignments[db.Key(giver_key)]))
      task = Task(url='/tasks/email', params={
          'giver': giver_key,
          'receiver': receiver_key,
          'creator': creator_key,
          'email_body': email_body})
      task.add('email-throttle')
    else:
      # send to everybody
      for key,value in assignments.iteritems():
        giver_key = urllib.quote(str(key))
        receiver_key = urllib.quote(str(value))
        task = Task(url='/tasks/email', params={
            'giver': giver_key,
            'receiver': receiver_key,
            'creator': creator_key,
            'email_body': email_body})
        task.add('email-throttle')

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class EmailWorker(BaseHandler):
  def post(self):
    if self.request.get("is_creator_email", "False") == "True":
      self.send_creator_email()
    else:
      self.send_assignment_email()

  def send_creator_email(self):
      creator = urllib.unquote(self.request.get('creator'))
      code = urllib.unquote(self.request.get('code'))

      creator_obj = db.get(db.Key(creator))

      self.add_template_value("creator",
                              creator_obj.name
                              + " ("
                              + creator_obj.email
                              + ")")
      self.add_template_value("code", code)

      html_body = template.render(os.path.join(os.path.dirname(__file__),
                                               "confirm_email.html"),
                                  self.template_values)
      mail.send_mail(sender="jesse.shieh@gmail.com",
                     to=creator_obj.email,
                     subject="Your Secret Santa Gift Exchange",
                     body=html_body,
                     html=html_body)

  def send_assignment_email(self):
      giver_key = urllib.unquote(self.request.get('giver'))
      receiver_key = urllib.unquote(self.request.get('receiver'))
      creator_key = urllib.unquote(self.request.get('creator'))
      email_body = urllib.unquote(self.request.get('email_body'))

      giver_obj = db.get(db.Key(giver_key))
      receiver_obj = db.get(db.Key(receiver_key))
      creator_obj = db.get(db.Key(creator_key))

      if giver_obj.name == '':
        giver = giver_obj.email
      else:
        giver = giver_obj.name + " (" + giver_obj.email + ")"

      if receiver_obj.name == '':
        receiver = receiver_obj.email
      else:
        receiver = receiver_obj.name + " (" + receiver_obj.email + ")"

      self.add_template_value("giver", giver)
      self.add_template_value("receiver", receiver)
      self.add_template_value("email_body", email_body)
      html_body = template.render(os.path.join(os.path.dirname(__file__),
                                               "invitee_email.html"),
                                  self.template_values)
      mail.send_mail(sender="jesse.shieh@gmail.com",
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
    creator_key = urllib.quote(str(creator.key()))
    code = urllib.quote(str(game.key()))
    task = Task(url='/tasks/email', params={
        'is_creator_email': 'True',
        'creator': creator_key,
        'code': code})
    task.add('email-throttle')

    # render
    assignments = self.create_assignment_dictionary(invitees)
    self.add_template_value("assignments", assignments)
    self.add_template_value("code", code)
    self.add_template_value("email_body", game.email_body)
    self.render("confirm.html")

class SaveEmailHandler(BaseHandler):
  def post(self):
    code = urllib.unquote(self.request.get("code"))
    email_body = urllib.unquote(self.request.get("email_body"))

    game = db.get(db.Key(code))
    game.email_body = email_body
    game.put()

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

def main():
  # boilerplate application registration stuff
  application = webapp.WSGIApplication([("/", MainHandler),
                                        ("/email", EmailHandler),
                                        ("/confirm", ConfirmHandler),
                                        ("/manage", ManageHandler),
                                        ("/tasks/email", EmailWorker),
                                        ("/save/email", SaveEmailHandler)],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()