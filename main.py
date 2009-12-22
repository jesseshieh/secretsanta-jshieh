#!/usr/bin/env python
# author: Jesse Shieh (jesse.shieh@gmail.com)

import Cookie
import logging
import os
import random
import re
import time
import urllib
import wsgiref.handlers
from blacklist import BlacklistGraph, NoCycleFoundError, randomize_list
from datetime import datetime, timedelta
from google.appengine.api import mail
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import db
from google.appengine.ext.db import BadKeyError
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
import facebook

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

  def is_blacklisted(self, person):
    """
    Returns if person is blacklisted
    """
    if not self.blacklist:
      return False
    return person in self.blacklist

class Game(db.Model):
  creation_time = db.DateTimeProperty(auto_now_add=True)
  last_modified_time = db.DateTimeProperty(auto_now=True)
  creator = db.ReferenceProperty(Person)
  invitees = db.ListProperty(db.Key) # list of Persons
  assignments = db.ListProperty(db.Key) # list of Persons in assignment order (objects not keys)

  # list of Persons that are participating.  x gives gift to x+1
  signup_deadline = db.DateTimeProperty()
  exchange_date = db.DateTimeProperty()
  price = db.FloatProperty(default=0.0)
  location = db.StringProperty()
  invitation_message = db.TextProperty()

class AnonymousMessage(db.Model):
  creation_time = db.DateTimeProperty(auto_now_add=True)
  last_modified_time = db.DateTimeProperty(auto_now=True)
  message = db.TextProperty()
  receiver = db.ReferenceProperty(reference_class=Person, collection_name="received_messages")
  sender = db.ReferenceProperty(reference_class=Person, collection_name="sent_messages")
  from_secret_santa = db.BooleanProperty()

  def __cmp__(self, other):
    """Sets the sort order of these by creation_time.  Needed for SignupHandler"""
    return cmp(self.creation_time, other.creation_time)

class PublicMessage(db.Model):
  creation_time = db.DateTimeProperty(auto_now_add=True)
  last_modified_time = db.DateTimeProperty(auto_now=True)
  message = db.TextProperty()
  sender = db.ReferenceProperty(reference_class=Person, collection_name="public_messages")
  game = db.ReferenceProperty(reference_class=Game, collection_name="public_messages")

class BaseHandler(webapp.RequestHandler):
  """
  BaseHandler class which all other handlers decend from.
  Implements some commonly useful functions
  """
  template_values = {
    "title": "Secret Santa Organizer: Easier than pulling names from a hat.",
    "theme": "ui-lightness",
    "meta_description": "Planning a secret santa? Do it here. Great for co-workers, friends, or family. Easier than pulling names from a hat.  No need to get everyone in the same room.  Names are pulled automatically on the sign-up deadline by computer.  Participants can respond yes or no and provide a gift hint, blacklist others, and send messages.",
    "meta_keywords": "plan planner event gifts gift ideas give online secret santa generator exchange organizer organize organise organiser set up setup create game",
    }

  def maybe_show_flash(self):
    """
    Most get() methods will have this at the top to show the flash
    message if it exists and clear it
    """
    if self.has_flash():
      self.add_template_value("flash", self.get_flash())
      self.clear_flash()

    if self.has_error():
      self.add_template_value("error", self.get_error())
      self.clear_error()

  def add_template_value(self, key, value):
    """
    adds a new entry in the template dictionary
    """
    self.template_values[key] = value

  def add_template_value_from_request(self, key):
    """
    special case of add_template_value that pulls the value from the
    request object (it's a url parameter of the same name)
    """
    self.add_template_value(key, self.request.get(key))

  def render(self, template_name):
    """
    renders and writes the response given the template name
    """
    path = os.path.join(os.path.dirname(__file__), template_name)
    self.response.out.write(template.render(path, self.template_values))

  def add_flash(self, message):
    """
    Send a flash message that shows only once to the user
    """
    cookie = Cookie.SimpleCookie()
    cookie["flash"] = message
    cookie["flash"]["Path"] = "/"

    h = re.compile('^Set-Cookie:').sub('', cookie.output(), count=1)
    self.response.headers.add_header('Set-Cookie', str(h))

  def add_error(self, message):
    """
    Send a flash message that shows only once to the user
    """
    cookie = Cookie.SimpleCookie()
    cookie["error"] = message
    cookie["error"]["Path"] = "/"

    h = re.compile('^Set-Cookie:').sub('', cookie.output(), count=1)
    self.response.headers.add_header('Set-Cookie', str(h))

  def add_extra_data(self, message):
    """
    Send a flash message that shows only once to the user
    """
    cookie = Cookie.SimpleCookie()
    cookie["extra_data"] = message
    cookie["extra_data"]["Path"] = "/"

    h = re.compile('^Set-Cookie:').sub('', cookie.output(), count=1)
    self.response.headers.add_header('Set-Cookie', str(h))

  def clear_flash(self):
    self.add_flash("")

  def clear_error(self):
    self.add_error("")

  def clear_extra_data(self):
    self.add_extra_data("")

  def has_flash(self):
    return self.request.cookies.has_key("flash")

  def has_error(self):
    return self.request.cookies.has_key("error")

  def has_extra_data(self):
    return self.request.cookies.has_key("extra_data")

  def get_flash(self):
    if self.has_flash():
      return self.request.cookies["flash"].strip('\'"')
    else:
      return None

  def get_error(self):
    if self.has_error():
      return self.request.cookies["error"].strip('\'"')
    else:
      return None

  def get_extra_data(self):
    if self.has_extra_data():
      return self.request.cookies["extra_data"].strip('\'"')
    else:
      return None

  def get_new_blacklist_from_request(self):
    """
    Get blacklist entries from the URL and return a blacklist
    list object, ready for the Person object
    """
    blacklist = []
    invitee_email_re = re.compile(r"blacklist(\d+)")
    for key in self.request.arguments():
      if invitee_email_re.match(key):
        invitee_key = self.request.get(key)
        blacklist.append(db.Key(invitee_key))
    return blacklist

  def has_duplicate_invitee(self, game, email):
    """
    Returns if there is another invitee in this game with the
    same email address
    """
    for invitee_key in game.invitees:
      invitee = db.get(invitee_key)
      if invitee.email.lower() == email.lower():
        self.add_error("%s has already been invited." % email)
        return True
    return False

  # TODO(jesses): consider putting this in a more appropriate class
  def get_assignment_dict(self, invitee_keys):
    """
    Translates an array of keys that pertain to invitees and
    translates it into a dictionary of giver -> receiver assignments.

    The order of the translation is simply i -> i + 1

    >>> handler = BaseHandler()
    >>> handler.get_assignment_dict([1, 2, 3])
    hello
    """
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
    self.maybe_show_flash()
    default_exchange_date = datetime.today() + timedelta(days=14)
    default_signup_deadline = datetime.today() + timedelta(days=7)
    self.add_template_value("price", "50.00")
    self.add_template_value("location", "TBD")
    self.add_template_value("exchange_date",
                            default_exchange_date.strftime("%m/%d/%Y"))
    self.add_template_value("signup_deadline",
                            default_signup_deadline.strftime("%m/%d/%Y"))
    self.render("main.html")

class AboutHandler(BaseHandler):
  def get(self):
    self.render("about.html")

class FaqHandler(BaseHandler):
  def get(self):
    self.render("faq.html")

class TermsHandler(BaseHandler):
  def get(self):
    self.render("terms.html")

class PrivacyHandler(BaseHandler):
  def get(self):
    self.render("privacy.html")

class SitemapHandler(BaseHandler):
  def get(self):
    self.render("sitemap.html")

class ManageHandler(BaseHandler):
  def get(self):
    self.maybe_show_flash()

    self.add_template_value("from_create", "")
    if self.has_extra_data():
      if self.get_extra_data() == "from_create":
        self.add_template_value("from_create", "True")
        self.clear_extra_data()

    code = self.request.get("code")
    if not code or code.isspace():
      self.add_template_value("error_message", "Missing code")
      self.render("error.html")
      return

    try:
      game = db.get(db.Key(code))
    except BadKeyError:
      self.add_template_value("error_message", "%s is an invalid code" % code)
      self.render("error.html")
      return

    assignments = self.get_assignment_dict(game.assignments)
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
    self.add_template_value("signup_deadline_passed", game.assignments)
    self.add_template_value("signup_deadline",
                            game.signup_deadline.strftime("%m/%d/%Y"))
    self.add_template_value("exchange_date",
                            game.exchange_date.strftime("%m/%d/%Y"))
    self.add_template_value("exchange_date_full",
                            game.exchange_date.strftime("%I:%M%p on %m/%d/%Y"))
    self.add_template_value("exchange_hour",
                            game.exchange_date.strftime("%I"))
    self.add_template_value("exchange_min",
                            game.exchange_date.strftime("%M"))
    self.add_template_value("exchange_ampm",
                            game.exchange_date.strftime("%p"))

    self.render("manage.html")

class SignupHandler(BaseHandler):
  def remove(self, obj_list, key):
    """
    For a list of Person objects, remove the one with the specified key.
    This is a key obj, not a key string.  Returns the new list.
    """
    # this would be easier if it were keys instead of objects
    # then i could just use blacklist_options.index(key) instead of
    # manually looping through
    for obj in obj_list:
      if obj.key() == key:
        obj_list.remove(obj)
    return obj_list

  def get(self):
    self.maybe_show_flash()
    invitee_key = self.request.get("invitee_key")

    if not invitee_key or invitee_key.isspace():
      self.add_template_value("error_message", "Missing key")
      self.render("error.html")
      return

    try:
      invitee_obj = db.get(db.Key(invitee_key))
    except BadKeyError:
      self.add_template_value("error_message", "%s is an invalid key" % invitee_key)
      self.render("error.html")
      return

    game = invitee_obj.game
    if not invitee_obj.signed_up and game.assignments:
      self.add_template_value("error_message", "Sorry, the sign-up deadline has already passed.  You can no longer sign up.")
      self.render("error.html")
      return

    invitee_objs = []
    for invitee_key in game.invitees:
      invitee_objs.append(db.get(invitee_key))

    blacklist = []
    blacklist_options = invitee_objs

    # you can't add yourself to your own blacklist
    blacklist_options = self.remove(blacklist_options, invitee_obj.key())

    for invitee_key in invitee_obj.blacklist:
      blacklist.append(db.get(invitee_key))

      # remove this one from the blacklist_options
      blacklist_options = self.remove(blacklist_options, invitee_key)

    assignment = None
    if game.assignments:
      assignments = self.get_assignment_dict(game.assignments)
      for giver, receiver in assignments.iteritems():
        if str(giver.key()) == str(invitee_obj.key()):
          assignment = receiver
        if str(receiver.key()) == str(invitee_obj.key()):
          secret_santa = giver

      messages_with_secret_santa = [x for x in invitee_obj.received_messages.filter("from_secret_santa =", True)]
      messages_with_secret_santa.extend([x for x in invitee_obj.sent_messages.filter("from_secret_santa =", False)])
      messages_with_secret_santa.sort()

      messages_with_assignment = [x for x in invitee_obj.received_messages.filter("from_secret_santa =", False)]
      messages_with_assignment.extend([x for x in invitee_obj.sent_messages.filter("from_secret_santa =", True)])
      messages_with_assignment.sort()
      self.add_template_value("messages_with_secret_santa", messages_with_secret_santa)
      self.add_template_value("messages_with_assignment", messages_with_assignment)

    public_messages = game.public_messages.order("creation_time")

    self.add_template_value("public_messages", public_messages)
    self.add_template_value("participant", invitee_obj)
    self.add_template_value("assignment", assignment)
    self.add_template_value("blacklist", blacklist)
    self.add_template_value("blacklist_options", blacklist_options)
    self.add_template_value("invitees", invitee_objs)
    self.add_template_value("code", game.key())
    self.add_template_value("price", "%.2f" % game.price)
    self.add_template_value("location", game.location)
    self.add_template_value("signup_deadline",
                            game.signup_deadline.strftime("%m/%d/%Y"))
    self.add_template_value("exchange_date",
                            game.exchange_date.strftime("%I:%M%p on %m/%d/%Y"))
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

    task = Task(url='/tasks/email/invitation', params={
        'code': code,
        'invitee_key': invitee_key,
        })
    task.add('email-throttle')

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class MessageEmailHandler(BaseHandler):
  def post(self):
    logging.debug("Entering MessageEmailHandler post()")
    invitee_key = self.request.get('invitee_key')
    to_secret_santa = self.request.get('to_secret_santa')
    message = self.request.get('message')
    code = self.request.get('code')
    for key in self.request.arguments():
      logging.debug("arg[%s]: %s" % (key, self.request.get(key)))

    try:
      invitee_obj = db.get(db.Key(invitee_key))
    except BadKeyError:
      self.add_flash("Sorry, there was a problem sending your message. We're working hard to fix it. Please try again later.")
      self.redirect("/signup?invitee_key=%s" % invitee_key)
      return

    task = Task(url='/tasks/email/message', params={
        'invitee_key': invitee_key,
        'to_secret_santa': to_secret_santa,
        'message': message,
        'code': code,
        })
    task.add('email-throttle')

    game = db.get(db.Key(code))

    assignments = self.get_assignment_dict(game.assignments)

    for giver, receiver in assignments.iteritems():
      if str(giver.key()) == invitee_key:
        my_assignment = receiver
      elif str(receiver.key()) == invitee_key:
        my_secret_santa = giver

    if to_secret_santa:
      recipient = my_secret_santa
    else:
      recipient = my_assignment

    anonymous_message = AnonymousMessage(
      message=message.replace('\n', '<br/>'),
      receiver=recipient,
      sender=invitee_obj,
      from_secret_santa=(not to_secret_santa))
    anonymous_message.put()

    self.add_flash("Message Sent.")
    self.redirect("/signup?invitee_key=%s" % invitee_key)
    logging.debug("Exiting MessageEmailHandler post()")

class PostPublicMessageHandler(BaseHandler):
  def post(self):
    logging.debug("Entering PostPublicMessageHandler post()")
    sender_key = self.request.get('sender_key')
    message = self.request.get('message')
    code = self.request.get('code')

    game = db.get(db.Key(code))
    for invitee_key in game.invitees:
      if str(invitee_key) == str(sender_key):
        continue
      task = Task(url='/tasks/email/public_message', params={
          'invitee_key': invitee_key,
          'sender_key': sender_key,
          'message': message,
          'code': code,
          })
      task.add('email-throttle')

    sender_obj = db.get(db.Key(sender_key))

    public_message = PublicMessage(
      message=message.replace('\n', '<br/>'),
      sender=sender_obj,
      game=game)
    public_message.put()

    self.add_flash("Message Posted.")
    self.redirect("/signup?invitee_key=%s" % sender_key)
    logging.debug("Exiting PostPublicMessageHandler post()")

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
    signedup_only = self.request.get('signedup_only')

    game = db.get(db.Key(code))

    for invitee_key in game.invitees:
      invitee_obj = db.get(invitee_key)
      if signedup_only and not invitee_obj.signed_up:
        # not signed up
        continue

      task = Task(url='/tasks/email/notification', params={
          'code': code,
          'invitee_key': str(invitee_key),
          'message': message,
          'subject': "Notification about your Secret Santa Gift Exchange",
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
      self.add_template_value("signup_deadline",
                              game.signup_deadline.strftime("%m/%d/%Y"))

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
    self.add_template_value("invitation_message", game.invitation_message)
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

class MessageEmailWorker(BaseHandler):
  def post(self):
    logging.debug("Entering MessageEmailWorker post()")

    invitee_key = self.request.get('invitee_key')
    to_secret_santa = self.request.get('to_secret_santa')
    message = self.request.get('message')
    code = self.request.get('code')

    invitee_obj = db.get(db.Key(invitee_key))
    game = db.get(db.Key(code))

    assignments = self.get_assignment_dict(game.assignments)

    for giver, receiver in assignments.iteritems():
      if str(giver.key()) == invitee_key:
        my_assignment = receiver
      elif str(receiver.key()) == invitee_key:
        my_secret_santa = giver

    if to_secret_santa:
      recipient = my_secret_santa
      sender = "your assignment"
      non_sender = "your secret santa"
    else:
      recipient = my_assignment
      sender = "your secret santa"
      non_sender = "your assignment"

    logging.debug("sending message from %s to %s" % (invitee_obj, recipient))
    self.add_template_value("message", message)
    self.add_template_value("sender", sender)
    self.add_template_value("non_sender", non_sender)
    self.add_template_value("recipient", recipient)
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "message_email.html"),
                                self.template_values)
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to=recipient.email,
                   subject="Message from %s" % sender,
                   body=html_body,
                   html=html_body)

    logging.debug("Exiting MessageEmailWorker post()")

class PublicMessageEmailWorker(BaseHandler):
  def post(self):
    logging.debug("Entering PublicMessageEmailWorker post()")

    sender_key = self.request.get('sender_key')
    invitee_key = self.request.get('invitee_key')
    message = self.request.get('message')
    code = self.request.get('code')

    sender_obj = db.get(db.Key(sender_key))
    invitee_obj = db.get(db.Key(invitee_key))
    game = db.get(db.Key(code))

    self.add_template_value("message", message)
    self.add_template_value("sender", sender_obj)
    self.add_template_value("recipient", invitee_obj)
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "public_message_email.html"),
                                self.template_values)
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to=invitee_obj.email,
                   subject="Post to Message Board from %s" % sender_obj,
                   body=html_body,
                   html=html_body)

    logging.debug("Exiting PublicMessageEmailWorker post()")

class ReminderEmailWorker(BaseHandler):
  def post(self):
    invitee_key = self.request.get('invitee_key')
    subject = self.request.get('subject')
    code = self.request.get('code')

    game = db.get(db.Key(code))

    invitee_obj = db.get(db.Key(invitee_key))
    self.add_template_value("invitee", invitee_obj)
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "reminder_email.html"),
                                self.template_values)
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to=invitee_obj.email,
                   subject=subject,
                   body=html_body,
                   html=html_body)

class NotificationEmailWorker(BaseHandler):
  def post(self):
    invitee_key = self.request.get('invitee_key')
    message = self.request.get('message')
    subject = self.request.get('subject')
    code = self.request.get('code')
    show_manage_button = self.request.get('show_manage_button')

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
    self.add_template_value("show_manage_button", "show_manage_button")
    self.add_template_value("code", code)
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "notification_email.html"),
                                self.template_values)
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to=invitee_obj.email,
                   subject=subject,
                   body=html_body,
                   html=html_body)

class AssignmentEmailWorker(BaseHandler):
  def post(self):
    giver_key = self.request.get('giver_key')
    code = self.request.get('code')

    game = db.get(db.Key(code))

    assignments = self.get_assignment_dict(game.assignments)

    for giver, receiver in assignments.iteritems():
      if str(giver.key()) == giver_key:
        giver_obj = giver
        receiver_obj = receiver

    if not giver_obj or not receiver_obj:
      self.error(500)

    self.add_template_value("giver", giver_obj)
    self.add_template_value("receiver", receiver_obj)
    self.add_template_value("gift_hint", receiver_obj.gift_hint)
    self.add_template_value("exchange_date",
                            game.exchange_date.strftime("%I:%M%p on %m/%d/%Y"))
    html_body = template.render(os.path.join(os.path.dirname(__file__),
                                             "assignment_email.html"),
                                self.template_values)
    mail.send_mail(sender="Secret Santa Organizer <notify@secret-santa-organizer.com>",
                   to=giver_obj.email,
                   subject="Your Secret Santa Assignment",
                   body=html_body,
                   html=html_body)

class EmailRemindersWorker(BaseHandler):
  """
  Send out a reminder of the signup deadline 1 day beforehand
  """
  def get(self):
    # no need to convert this to PST because we really only care about days
    # not hours.  UTC will be in the same day as PST assuming this is run at
    # 00:00 PST.  UTC should be 8:00 PST
    now = datetime.now()

    one_day = timedelta(days=1)
    today = datetime.today()
    today_elapsed = timedelta(hours=today.hour,
                              minutes=today.minute,
                              seconds=today.second,
                              microseconds=today.microsecond)
    today = today - today_elapsed
    tomorrow = today + one_day
    logging.debug("today: %s" % today)
    logging.debug("tomorrow: %s" % tomorrow)

    games = Game.all().filter("signup_deadline >=", today).filter("signup_deadline <", tomorrow)
    logging.debug([x.signup_deadline for x in games])

    for game in games:
      if not game.signup_deadline:
        # no signup deadline.. either an old entry or some kind of error. skip
        logging.debug("%s: no signup deadline, skipping" & game.key())
        continue

      logging.debug(game.signup_deadline)
      if game.assignments:
        logging.debug("%s: assignments already generated, skipping" & game.key())
        continue

      for invitee_key in game.invitees:
        invitee_obj = db.get(invitee_key)
        if not invitee_obj.signed_up:
          task = Task(url='/tasks/email/reminder', params={
              'code': str(game.key()),
              'invitee_key': str(invitee_key),
              'subject': "Secret Santa Reminder: 1 Day Left to Respond",
              })
          task.add('email-throttle')

      # send the creator a reminder email too
      game.creator
      task = Task(url='/tasks/email/notification', params={
          'code': str(game.key()),
          'invitee_key': str(game.creator.key()),
          'show_manage_button': "True",
          'subject': 'Secret Santa Reminder: 1 Day Left',
          'message': "This is a reminder that there is only one day left for participants to respond yes or no to the invitation.  An email reminder was sent to people who didn't sign up, but you may want to give them an extra nudge.  Click below to see who has signed up.",
          })
      task.add('email-throttle')

class AssignmentsNotPossibleError(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)

class GenerateAssignmentsWorker(BaseHandler):
  def random_assignments(self, list):
    logging.debug("Entering random_assignments")
    while True:
      try:
        g = BlacklistGraph(list)
        logging.debug(g)
        cycle = g.random_cycle()
        logging.debug("cycle found:")
        for x in cycle: logging.debug(x)

        # convert back to keys
        logging.debug("Exiting random_assignments")
        return cycle
      except NoCycleFoundError:
        logging.debug("no cycle found")
        # remove a random blacklist entry until there are none left
        blacklist_found = False
        for participant in list:
          participant = db.get(participant)
          if participant.blacklist:
            blacklist_found = True
        if not blacklist_found:
          # no blacklists exist at all, this is a problem
          raise AssignmentsNotPossibleError, "%s" % list

        # blacklists still exist, remove a random one
        random_list = randomize_list(list)
        for participant in random_list:
          participant = db.get(participant)
          if participant.blacklist:
            # remove first element after randomizing
            participant.blacklist = randomize_list(participant.blacklist)
            logging.debug("removing blacklist %s to %s" % (participant,participant.blacklist[0]))
            participant.blacklist = participant.blacklist[1:]
            participant.put()
            break

        # continue with the infinite loop
    logging.debug("Exiting generate_assignments: this should never happen")

  def get(self):
    logging.debug("Entering GenerateAssignmentsWorker get()")

    # no need to convert this to PST because we really only care about days
    # not hours.  UTC will be in the same day as PST assuming this is run at
    # 00:00 PST.  UTC should be 8:00 PST
    now = datetime.now()

    one_day = timedelta(days=1)
    today = datetime.today()
    today_elapsed = timedelta(hours=today.hour,
                              minutes=today.minute,
                              seconds=today.second,
                              microseconds=today.microsecond)
    today = today - today_elapsed
    yesterday = today - one_day
    logging.debug("yesterday: %s" % yesterday)
    logging.debug("today: %s" % today)

    # go through all the games in the database
    # find the ones that have deadlines yesterday
    # generate the assignments, and send emails
    games = Game.all().filter("signup_deadline <", today).filter("signup_deadline >=", yesterday)
    logging.debug([x.signup_deadline for x in games])

    for game in games:
      if not game.signup_deadline:
        # no signup deadline.. either an old entry or some kind of error. skip
        logging.debug("%s: no signup_deadline, skipping" % game.key())
        continue

      if game.assignments:
        # already generated, skip
        logging.debug("%s: already generated, skipping" % game.key())
        continue

      logging.debug("signup deadline: %s" % game.signup_deadline)

      # these are the games that we should generate assignments for
      # convert to objs
      participants = []
      for invitee_key in game.invitees:
        if db.get(invitee_key).signed_up:
          participants.append(invitee_key)

      logging.debug(participants)
      try:
        participants = self.random_assignments(participants)
        game.assignments = participants
        game.put()

        # send emails
        for giver_key in game.assignments:
          task = Task(url='/tasks/email/assignment', params={
              'giver_key': giver_key,
              'code': str(game.key())})
          task.add('email-throttle')
      except AssignmentsNotPossibleError:
        task = Task(url='/tasks/email/notification', params={
            'code': str(game.key()),
            'invitee_key': str(game.creator.key()),
            'show_manage_button': "True",
            'subject': 'Problem with your Secret Santa Gift Exchange',
            'message': "Assignments could not be generated. There probably weren't enough people signed up.  Try extending the sign-up deadline and sending out a reminder to sign up.",
            })
        task.add('email-throttle')
    logging.debug("Exiting GenerateAssignmentsWorker get()")

class CreateHandler(BaseHandler):
  def post(self):
    # add these as template values so we can re-populate the form in case
    # it isn't valid
    for key in self.request.arguments():
      self.add_template_value_from_request(key)

    # no need to unescape these, they are from a form post.. ?
    creator_email = self.request.get("creator_email")
    creator_name = self.request.get("creator_name", "")
    invitation_message = urllib.unquote(self.request.get("invitation_message"))
    exchange_date = self.request.get("exchange_date")
    exchange_hour = self.request.get("exchange_hour")
    exchange_min = self.request.get("exchange_min")
    exchange_ampm = self.request.get("exchange_ampm")
    signup_deadline = self.request.get("signup_deadline")
    location = self.request.get("location")
    price = self.request.get("price")
    is_creator_participating = self.request.get("is_creator_participating", "True")

    if not creator_email or creator_email.isspace():
      self.add_error("You must specify an email for the organizer.")
      self.redirect("/")
      return

    m = re.match("^[$]?((\d+)([.]\d{2})?)$", price)
    price = float(m.group(1))
    try:
      signup_deadline = datetime.strptime(signup_deadline + " 11:59PM", "%m/%d/%Y %I:%M%p")
    except ValueError:
      self.add_error("Looks like the sign-up deadline is invalid.")
      self.redirect("/")
      return

    try:
      exchange_date = datetime.strptime("%s %s:%s%s" % (exchange_date, exchange_hour, exchange_min, exchange_ampm), "%m/%d/%Y %I:%M%p")
    except ValueError:
      self.add_error("Looks like the exchange date is invalid.")
      self.redirect("/")
      return

    if exchange_date < signup_deadline:
      self.add_error("The exchange date needs to be after the sign-up deadline.")
      self.redirect("/")
      return

    logging.debug(exchange_date)
    is_creator_participating = (is_creator_participating == "True")

    # it sucks that we have to put() this, but we need the key() to initialize
    # the Person objects.  when there is an error, we have to delete() the
    # game
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
        id = int(email_match.group(1))
      elif name_match:
        id = int(name_match.group(1))
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

    # convert invitees from dictionary to array
    new_invitees = []
    for key, value in invitees.items():
      new_invitees.append(value)
    invitees = new_invitees

    # check for duplicates, reject if found
    # skip item 0 because that's the creator.  it's okay for them to have
    # duplicates since that's a ui problem
    for i in range(1, len(invitees)):
      for j in range(i + 1, len(invitees)):
        if invitees[j].email.lower() == invitees[i].email.lower():
          # duplicate found
          game.delete()
          self.add_error("Looks like you entered %s more than once.  Try again." % invitees[j].email)
          self.redirect("/")
          return

    # remove duplicates of the creator
    r = range(1, len(invitees))
    r.reverse()
    for i in r:
      if invitees[i].email.lower() == creator.email.lower():
        logging.debug("removing %s from invitee list because he/she is the creator", invitees[i])
        invitees.pop(i)

    invitee_keys = []
    for invitee in invitees:
      invitee.put()
      invitee_keys.append(invitee.key())

    # insert game into datastore
    game.creator = creator
    game.invitees = invitee_keys
    game.price = price
    game.location = location
    game.exchange_date = exchange_date
    game.signup_deadline = signup_deadline
    game.invitation_message = db.Text(invitation_message)
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

    self.add_flash("Event was created successfully.  Invitations have been sent.")
    self.add_extra_data("from_create")
    self.redirect("/manage?code=%s" % code)

class SaveDetailsHandler(BaseHandler):
  def post(self):
    code = self.request.get("code")
    exchange_date = self.request.get("exchange_date")
    exchange_hour = self.request.get("exchange_hour")
    exchange_min = self.request.get("exchange_min")
    exchange_ampm = self.request.get("exchange_ampm")
    signup_deadline = self.request.get("signup_deadline")
    location = self.request.get("location")
    price = self.request.get("price")
    send_edit_details_message = self.request.get("send_edit_details_message")
    edit_details_message = self.request.get("edit_details_message")

    m = re.match("^[$]?((\d+)([.]\d{2})?)$", price)
    price = float(m.group(1))

    try:
      signup_deadline = datetime.strptime(signup_deadline + " 11:59PM", "%m/%d/%Y %I:%M%p")
    except ValueError:
      self.add_error("Looks like the sign-up deadline is invalid.")
      self.redirect("/manage?code=%s" % code)
      return

    try:
      exchange_date = datetime.strptime("%s %s:%s%s" % (exchange_date, exchange_hour, exchange_min, exchange_ampm), "%m/%d/%Y %I:%M%p")
    except ValueError:
      self.add_error("Looks like the sign-up deadline is invalid.")
      self.redirect("/manage?code=%s" % code)
      return

    if exchange_date < signup_deadline:
      self.add_error("The exchange date needs to be after the sign-up deadline.")
      self.redirect("/manage?code=%s" % code)
      return

    game = db.get(db.Key(code))
    game.price = price
    game.location = location
    game.signup_deadline = signup_deadline
    game.exchange_date = exchange_date
    game.put()

    message = "Some event dates or details have been modified."
    if edit_details_message:
      message = message + "<br><br>Message from the creator:<br>\"%s\"" % edit_details_message

    if send_edit_details_message:
      for invitee_key in game.invitees:
        task = Task(url='/tasks/email/notification', params={
            'code': code,
            'invitee_key': str(invitee_key),
            'subject': 'Updates to Your Secret Santa Gift Exchange',
            'message': message,
            })
        task.add('email-throttle')
      self.add_flash("Details were saved successfully. Update Messages Sent.")
    else:
      self.add_flash("Details were saved successfully.")

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
    by_manager = self.request.get("by_manager")
    participant_key = self.request.get("participant_key")
    continue_url = self.request.get("continue_url")
    name = self.request.get("name")
    gift_hint = self.request.get("gift_hint")
    blacklist = self.get_new_blacklist_from_request()

    participant = db.get(db.Key(participant_key))
    participant.signed_up = False
    if name:
      participant.name = name
    if gift_hint:
      participant.gift_hint = gift_hint
    if blacklist:
      participant.blacklist = blacklist
    participant.put()

    if by_manager:
      self.add_flash("%s is no longer signed up." % participant.email)
    else:
      self.add_flash("You are no longer signed up.")

    if continue_url:
      self.redirect(continue_url)
    else:
      self.redirect("/manage?code=%s" % code)

class AddParticipantHandler(BaseHandler):
  def post(self):
    code = self.request.get("code")
    by_manager = self.request.get("by_manager")
    participant_key = self.request.get("participant_key")
    continue_url = self.request.get("continue_url")
    name = self.request.get("name")
    gift_hint = self.request.get("gift_hint")
    blacklist = self.get_new_blacklist_from_request()

    participant = db.get(db.Key(participant_key))
    participant.signed_up = True
    if name:
      participant.name = name
    if gift_hint:
      participant.gift_hint = gift_hint
    if blacklist:
      participant.blacklist = blacklist
    participant.put()

    if by_manager:
      self.add_flash("%s is now signed up." % participant.email)
    else:
      if self.request.get("save_only", "False") == "True":
        self.add_flash("Saved.")
      else:
        one_day = timedelta(days=1)
        email_day = participant.game.signup_deadline + one_day
        self.add_flash("You are signed-up.  Now just wait for an email on %s with your assignment." % email_day.strftime("%m/%d/%Y"))

    if continue_url:
      self.redirect(continue_url)
    else:
      self.response.headers["Content-Type"] = "text/plain"
      self.response.out.write("OK")

class AddInviteeHandler(BaseHandler):
  def post(self):
    code = self.request.get("code")
    invitee_email = self.request.get("invitee_email")
    continue_url = self.request.get("continue_url")

    game = db.get(db.Key(code))
    if not self.has_duplicate_invitee(game, invitee_email):
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
      self.add_flash("Invitation sent to %s" % invitee)

    if continue_url:
      self.redirect(continue_url)
    else:
      self.redirect("/manage?code=%s" % code)

class SaveInvitationMessageHandler(BaseHandler):
  def post(self):
    code = urllib.unquote(self.request.get("code"))
    invitation_message = urllib.unquote(self.request.get("invitation_message"))

    game = db.get(db.Key(code))
    game.invitation_message = db.Text(invitation_message)
    game.put()

    self.response.headers["Content-Type"] = "text/plain"
    self.response.out.write("OK")

class FacebookHandler(BaseHandler):
  FB_SECRET_KEY = "69289481278fe623a928413af4493870"
  FB_API_KEY = "6a691e1b214195d0c7bac825be30d7bc"

  def post(self):
    logging.debug("Entering FacebookHandler get()")
    self.facebookapi = facebook.Facebook(self.FB_API_KEY, self.FB_SECRET_KEY)

    if not self.facebookapi.check_session(self.request):
      logging.debug("redirecting to install")
      url = self.facebookapi.get_add_url()
      self.response.out.write('<fb:redirect url="' + url + '" />')
      return

    # Get the information about the user.
    info = self.facebookapi.users.getInfo([self.facebookapi.uid])
    logging.debug(info)

    html_escape_table = {
          "&": "&amp;",
              '"': "&quot;",
              "'": "&apos;",
              ">": "&gt;",
              "<": "&lt;",
              }

    def html_escape(text):
      """Produce entities within text."""
      return "".join(html_escape_table.get(c,c) for c in text)

    self.add_template_value(
      "invitation_content",
      html_escape("Come participant in my secret santa gift exchange! <fb:req-choice url=\"http://apps.facebook.com/secretsantaorganizer\" label=\"Accept Invitation\"/>"))

    self.render('facebook.html')
    logging.debug("Exiting FacebookHandler get()")

def main():
  # boilerplate application registration stuff
  logging.getLogger().setLevel(logging.DEBUG)
  application = webapp.WSGIApplication([("/", MainHandler),
                                        ("/create", CreateHandler),
                                        ("/manage", ManageHandler),
                                        ("/signup", SignupHandler),
                                        ("/facebook/", FacebookHandler),

                                        # static pages
                                        ("/about", AboutHandler),
                                        ("/faq", FaqHandler),
                                        ("/terms", TermsHandler),
                                        ("/privacy", PrivacyHandler),
                                        ("/sitemap", SitemapHandler),

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
                                        ("/email/message", MessageEmailHandler),
                                        ("/email/notification", NotificationEmailHandler),
                                        ("/email/assignment", AssignmentEmailHandler),
                                        ("/email/creation", CreationEmailHandler),
                                        ("/post/public_message", PostPublicMessageHandler),

                                        # taskqueue tasks
                                        ("/tasks/email/invitation", InvitationEmailWorker),
                                        ("/tasks/email/message", MessageEmailWorker),
                                        ("/tasks/email/notification", NotificationEmailWorker),
                                        ("/tasks/email/assignment", AssignmentEmailWorker),
                                        ("/tasks/email/creation", CreationEmailWorker),
                                        ("/tasks/email/reminder", ReminderEmailWorker),
                                        ("/tasks/email/public_message", PublicMessageEmailWorker),

                                        # cron jobs
                                        ("/tasks/generate/assignments", GenerateAssignmentsWorker),
                                        ("/tasks/email/reminders", EmailRemindersWorker),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()

