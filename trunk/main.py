#!/usr/bin/env python
# author: Jesse Shieh (jesse.shieh@gmail.com)

import logging
import os
import random
import re
import time
import urllib
import wsgiref.handlers
from datetime import datetime
from google.appengine.api import mail
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

debug_mode = True

class Person(db.Model):
  creation_time = db.DateTimeProperty(auto_now_add=True)
  last_modified_time = db.DateTimeProperty(auto_now=True)
  game = db.ReferenceProperty(db.Model, required=True)
  email = db.EmailProperty(required=True)
  name = db.StringProperty(default="")
  signed_up = db.BooleanProperty(default=False)
  gift_hint = db.StringProperty(default="")
  blacklist = db.ListProperty(db.Key) # list of people they don't want

  def __str__(self):
    if not self.name or self.name.isspace():
      return self.email
    else:
      return "%s (%s)" % (self.name, self.email)

class Game(db.Model):
  creation_time = db.DateTimeProperty(auto_now_add=True)
  last_modified_time = db.DateTimeProperty(auto_now=True)
  creator = db.ReferenceProperty(Person)
  invitees = db.ListProperty(db.Key) # list of Persons

  # list of Persons that are participating.  x gives gift to x+1
  signup_deadline = db.DateTimeProperty()
  exchange_date = db.DateTimeProperty()
  price = db.FloatProperty(default=0.0)
  location = db.StringProperty()
  invitation_message = db.StringProperty(multiline=True, default="")

class BaseHandler(webapp.RequestHandler):
  template_values = {
    "title": "Secret Santa Organizer",
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
  def get_assignments(self, invitee_keys):
    invitee_objs = []
    for key in invitee_keys:
      invitee_obj = db.get(key)
      if invitee_obj.signed_up:
        invitee_objs.append(invitee_obj)

    assignments = {}
    if len(invitee_objs) > 0:
      for i in range(len(invitee_objs) - 1):
        assignments[invitee_objs[i]] = invitee_objs[i + 1]
      assignments[invitee_objs[-1]] = invitee_objs[0]
    return assignments

class MainHandler(BaseHandler):
  def get(self):
    self.render("main.html")

class ManageHandler(BaseHandler):
  def get(self):
    code = self.request.get("code")
    if not code or code.isspace():
      self.response.out.write("Missing code")
      return

    game = db.get(db.Key(code))

    assignments = self.get_assignments(game.invitees)
    invitees = []
    for invitee_key in game.invitees:
      invitees.append(db.get(invitee_key))

    participants = []
    for invitee_keyobj in game.invitees:
      invitee = db.get(invitee_keyobj)
      if invitee.signed_up:
        participants.append(invitee)

    self.add_template_value("assignments", assignments)
    self.add_template_value("invitees", invitees)
    self.add_template_value("participants", participants)
    self.add_template_value("code", code)
    self.add_template_value("invitation_message", game.invitation_message)
    self.add_template_value("price", "%.2f" % game.price)
    self.add_template_value("location", game.location)
    self.add_template_value("signup_deadline",
                            game.signup_deadline.strftime("%m/%d/%Y"))
    self.add_template_value("exchange_date",
                            game.exchange_date.strftime("%m/%d/%Y"))

    self.render("manage.html")

class SignupHandler(BaseHandler):
  def get(self):
    invitee_key = self.request.get("invitee_key")

    invitee_obj = db.get(db.Key(invitee_key))
    game = invitee_obj.game

    invitee_objs = []
    for invitee_key in game.invitees:
      invitee_objs.append(db.get(invitee_key))

    self.add_template_value("participant", invitee_obj)
    self.add_template_value("invitees", invitee_objs)
    self.add_template_value("code", game.key())
    self.add_template_value("price", "%.2f" % game.price)
    self.add_template_value("location", game.location)
    self.add_template_value("signup_deadline",
                            game.signup_deadline.strftime("%m/%d/%Y"))
    self.add_template_value("exchange_date",
                            game.exchange_date.strftime("%m/%d/%Y"))
    self.render("signup.html")

class CreationEmailHandler(BaseHandler):
  def post(self):
    code = self.request.get("code")
    task = Task(url='/tasks/email/creation', params={
        'code': code,
        })
    task.add('email-throttle')

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class InvitationEmailHandler(BaseHandler):
  def post(self):
    invitee_key = self.request.get('invitee_key')
    code = self.request.get('code')

    logging.info(invitee_key)

    task = Task(url='/tasks/email/invitation', params={
        'code': code,
        'invitee_key': invitee_key,
        })
    task.add('email-throttle')

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class AssignmentEmailHandler(BaseHandler):
  def post(self):
    giver_key = self.request.get('giver_key')
    code = self.request.get('code')

    task = Task(url='/tasks/email/assignment', params={
        'code': code,
        'giver_key': giver_key,
        })
    task.add('email-throttle')

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class NotificationEmailHandler(BaseHandler):
  def post(self):
    message = self.request.get('message')
    code = self.request.get('code')

    game = db.get(db.Key(code))

    for invitee_key in game.invitees:
      task = Task(url='/tasks/email/notification', params={
          'code': code,
          'invitee_key': str(invitee_key),
          'message': message,
          })
      task.add('email-throttle')

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class CreationEmailWorker(BaseHandler):
  def post(self):
      code = self.request.get('code')
      game = db.get(db.Key(code))
      creator_obj = game.creator

      self.add_template_value("creator", creator_obj)
      self.add_template_value("code", code)

      html_body = template.render(os.path.join(os.path.dirname(__file__),
                                               "creation_email.html"),
                                  self.template_values)
      mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                     to=creator_obj.email,
                     subject="Your Secret Santa Gift Exchange",
                     body=html_body,
                     html=html_body)

class InvitationEmailWorker(BaseHandler):
  def post(self):
    invitee_key = self.request.get('invitee_key')
    code = self.request.get('code')

    game = db.get(db.Key(code))

    invitee_obj = db.get(db.Key(invitee_key))

    self.add_template_value("price", game.price)
    self.add_template_value("signup_deadline",
                            game.signup_deadline.strftime("%m/%d/%Y %I:%M%p"))
    self.add_template_value("exchange_date",
                            game.exchange_date.strftime("%m/%d/%Y %I:%M%p"))
    self.add_template_value("location", game.location)
    self.add_template_value("invitation_message",
                            urllib.unquote(game.invitation_message))
    self.add_template_value("invitee", invitee_obj)
    self.add_template_value("creator", game.creator)
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "invitation_email.html"),
                                self.template_values)
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to=invitee_obj.email,
                   subject="Your Secret Santa Invitation",
                   body=html_body,
                   html=html_body)

class NotificationEmailWorker(BaseHandler):
  def post(self):
    invitee_key = self.request.get('invitee_key')
    message = self.request.get('message')
    code = self.request.get('code')

    game = db.get(db.Key(code))

    invitee_obj = db.get(db.Key(invitee_key))

    self.add_template_value("price", game.price)
    self.add_template_value("signup_deadline",
                            game.signup_deadline.strftime("%m/%d/%Y %I:%M%p"))
    self.add_template_value("exchange_date",
                            game.exchange_date.strftime("%m/%d/%Y %I:%M%p"))
    self.add_template_value("location", game.location)
    self.add_template_value("message", urllib.unquote(message))
    self.add_template_value("invitee", invitee_obj)
    self.add_template_value("creator", game.creator)
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "notification_email.html"),
                                self.template_values)
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to=invitee_obj.email,
                   subject="Updates To Your Secret Santa Gift Exchange",
                   body=html_body,
                   html=html_body)

class AssignmentEmailWorker(BaseHandler):
  def post(self):
    giver_key = self.request.get('giver_key')
    code = self.request.get('code')

    game = db.get(db.Key(code))

    assignments = self.get_assignments(game.invitees)

    giver_obj = db.get(db.Key(giver_key))
    receiver_obj = assignments[giver_obj]

    if not giver_obj or not receiver_obj:
      self.error(500)

    giver_obj = db.get(db.Key(giver_key))
    receiver_obj = db.get(db.Key(receiver_key))

    self.add_template_value("giver", giver_obj)
    self.add_template_value("receiver", receiver_obj)
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "assignment_email.html"),
                                self.template_values)
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to=giver_obj.email,
                   subject="Your Secret Santa Assignment",
                   body=html_body,
                   html=html_body)

class GenerateAssignmentsWorker(BaseHandler):
  def get(self):
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to="jesse.shieh@gmail.com",
                   subject="Your Secret Santa Cron Job",
                   body="has run",
                   html="has run")

class CreateHandler(BaseHandler):
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
    # no need to unescape these, they are from a form post.. ?
    creator_email = self.request.get("creator_email")
    creator_name = self.request.get("creator_name", "")
    invitation_message = self.request.get("invitation_message")
    exchange_date = self.request.get("exchange_date")
    signup_deadline = self.request.get("signup_deadline")
    location = self.request.get("location")
    price = self.request.get("price")
    is_creator_participating = self.request.get("is_creator_participating", "True")

    m = re.match("^[$]?((\d+)([.]\d{2})?)$", price)
    price = float(m.group(1))
    signup_deadline = datetime.strptime(signup_deadline + " 11:59pm", "%m/%d/%Y %I:%M%p")
    exchange_date = datetime.strptime(exchange_date + " 11:59pm", "%m/%d/%Y %I:%M%p")
    is_creator_participating = (is_creator_participating == "True")

    game = Game()
    game.put()

    creator = Person(email=creator_email,
                     name=creator_name,
                     game=game)

    invitees = {}

    # array of invitees (don't forget to add the creator)
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
        invitee = Person(email="required",
                         game=game)
        invitees[id] = invitee

      if email_match:
        invitees[id].email = value
      if name_match:
        invitees[id].name = value

    invitee_keys = []
    for key,invitee in invitees.iteritems():
      invitee.put()
      invitee_keys.append(invitee.key())

    # insert game into datastore
    game.creator = creator
    game.invitees = invitee_keys
    game.price = price
    game.location = location
    game.exchange_date = exchange_date
    game.signup_deadline = signup_deadline
    game.invitation_message = invitation_message
    game.put()

    # send creator email through email-throttle queue
    code = urllib.quote(str(game.key()))
    task = Task(url='/tasks/email/creation', params={
        'code': code})
    task.add('email-throttle')

    # send invitations
    for invitee_key in game.invitees:
      task = Task(url='/tasks/email/invitation', params={
          'invitee_key': str(invitee_key),
          'code': code})
      task.add('email-throttle')

    self.redirect("/manage?code=%s" % code)

class SaveDetailsHandler(BaseHandler):
  def post(self):
    code = self.request.get("code")
    exchange_date = self.request.get("exchange_date")
    signup_deadline = self.request.get("signup_deadline")
    location = self.request.get("location")
    price = self.request.get("price")

    m = re.match("^[$]?((\d+)([.]\d{2})?)$", price)
    price = float(m.group(1))
    signup_deadline = datetime.strptime(signup_deadline + " 11:59pm", "%m/%d/%Y %I:%M%p")
    exchange_date = datetime.strptime(exchange_date + " 11:59pm", "%m/%d/%Y %I:%M%p")

    game = db.get(db.Key(code))
    game.price = price
    game.location = location
    game.signup_deadline = signup_deadline
    game.exchange_date = exchange_date
    game.put()

    self.redirect("/manage?code=%s" % code)

class RemoveInviteeHandler(BaseHandler):
  # TODO(jesses): change this to post?
  # figure out how to do a post with javascript without a form
  def get(self):
    code = self.request.get("code")
    invitee_key = self.request.get("invitee_key")

    game = db.get(db.Key(code))
    game.invitees.remove(db.Key(invitee_key))
    game.put()

    self.redirect("/manage?code=%s" % code)

class RemoveParticipantHandler(BaseHandler):
  def post(self):
    code = self.request.get("code")
    participant_key = self.request.get("participant_key")
    continue_url = self.request.get("continue_url")

    participant = db.get(db.Key(participant_key))
    participant.signed_up = False
    participant.put()

    if continue_url:
      self.redirect(continue_url)
    else:
      self.redirect("/manage?code=%s" % code)

class AddParticipantHandler(BaseHandler):
  def post(self):
    code = self.request.get("code")
    participant_key = self.request.get("participant_key")
    continue_url = self.request.get("continue_url")
    name = self.request.get("name")
    gift_hint = self.request.get("gift_hint")
    blacklist = self.request.get("blacklist")

    participant = db.get(db.Key(participant_key))
    participant.signed_up = True
    participant.name = name
    participant.gift_hint = gift_hint
    if blacklist:
      participant.blacklist = [db.Key(blacklist)]
    participant.put()

    if continue_url:
      self.redirect(continue_url)
    else:
      self.redirect("/signup?invitee_key=%s" % participant_key)

class AddInviteeHandler(BaseHandler):
  # TODO(jesses): change this to post?
  # figure out how to do a post with javascript without a form
  def get(self):
    code = self.request.get("code")
    invitee_email = self.request.get("invitee_email")

    # TODO(jesses): make email unique so no duplicates are allowed for
    # a given game?
    game = db.get(db.Key(code))
    invitee = Person(email=invitee_email,
                     game=game)
    invitee.put()
    game.invitees.append(invitee.key())
    game.put()

    task = Task(url='/tasks/email/invitation', params={
        'code': code,
        'invitee_key': str(invitee.key()),
        })
    task.add('email-throttle')

    self.redirect("/manage?code=%s" % code)

class SaveInvitationMessageHandler(BaseHandler):
  def post(self):
    code = self.request.get("code")
    invitation_message = self.request.get("invitation_message")

    game = db.get(db.Key(code))
    game.invitation_message = invitation_message
    game.put()

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

def main():
  # boilerplate application registration stuff
  application = webapp.WSGIApplication([("/", MainHandler),
                                        ("/create", CreateHandler),
                                        ("/manage", ManageHandler),
                                        ("/signup", SignupHandler),

                                        # operate and redirect
                                        ("/save/details", SaveDetailsHandler),
                                        ("/remove/invitee", RemoveInviteeHandler),
                                        ("/remove/participant", RemoveParticipantHandler),
                                        ("/add/invitee", AddInviteeHandler),
                                        ("/add/participant", AddParticipantHandler),

                                        # asyncs
                                        ("/save/invitation_message", SaveInvitationMessageHandler),

                                        # email handlers
                                        ("/email/invitation", InvitationEmailHandler),
                                        ("/email/notification", NotificationEmailHandler),
                                        ("/email/assignment", AssignmentEmailHandler),
                                        ("/email/creation", CreationEmailHandler),

                                        # taskqueue tasks
                                        ("/tasks/email/invitation", InvitationEmailWorker),
                                        ("/tasks/email/notification", NotificationEmailWorker),
                                        ("/tasks/email/assignment", AssignmentEmailWorker),
                                        ("/tasks/email/creation", CreationEmailWorker),

                                        # cron jobs
                                        ("/tasks/generate/assignments", GenerateAssignmentsWorker),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()
