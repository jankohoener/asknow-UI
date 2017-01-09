# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -*- coding: utf-8 -*-

import webapp2
import jinja2
import os
import random
import json
import urllib
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
from google.appengine.api import memcache
import hashlib, uuid
import logging
import re


template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir), 
	autoescape = True)

class Handler(webapp2.RequestHandler):
	SECRET = "The AskNow secret"
	
	def write(self, *a, **kw):
		self.response.out.write(*a, **kw)
		
	def render_str(self, template, **params):
		t = jinja_env.get_template(template)
		return t.render(params)
		
	def render(self, template, **kw):
		self.write(self.render_str(template, **kw))
		
	def hash_str(self, s):
		return hashlib.sha256(self.SECRET + str(s)).hexdigest()
		
	def reset_cookie(self, cookie):
		self.response.headers.add_header('Set-Cookie', '%s=; Path=/' % cookie)
		
	def generate_salt(self):
		return uuid.uuid4().hex
		
	def generate_pwhash(self, password, salt):
		return hashlib.sha512(password + salt).hexdigest()
		
	def verify_password(self, pwhash, password, salt):
		return self.generate_pwhash(password, salt) == pwhash

		
class AskNowUser(ndb.Model):
	username = ndb.StringProperty(required = True)
	password = ndb.StringProperty(required = True)
	salt = ndb.StringProperty(required = True)
	email = ndb.StringProperty()
	created = ndb.DateTimeProperty(auto_now_add=True)
	
class AskNowQuestion(ndb.Model):
	userid = ndb.KeyProperty(AskNowUser)
	question = ndb.StringProperty()
	asked = ndb.DateTimeProperty(auto_now_add=True)
		
class AskNowDemoHandler(Handler):
	def retrieve_answer(self, q):
		params = { 'q': q }
		cur_answer = {}
		url = 'https://jankos-project.appspot.com/asknow/json?%s' % urllib.urlencode(params)
		try:
			result = urlfetch.fetch(url)
			if result.status_code == 200:
				cur_answer = json.loads(result.content)
				return cur_answer
			else:
				return None
		except urlfetch.Error:
			return None
	
	def get(self):
		logging.info('Start building demo page')
		q = self.request.get('q')
		auth = True
		cookie_data = self.request.cookies.get('userid')
		if cookie_data:
			logging.info('Cookie for userid is set, reading.')
			cookie_data_split = cookie_data.split('|')
			if len(cookie_data_split) == 2:
				logging.info('Cookie split at |, checking hash.')
				userkeystr = cookie_data_split[0]
				userhash = cookie_data_split[1]
				if self.hash_str(userkeystr) == userhash:
					auth = True
					logging.info('Authentification successful, retrieving user for id %s' % userkeystr)
					key = 'user-%s' % userkeystr
					user = memcache.get(key)
					if user:
						logging.info('User retrieved from cache.')
					else:
						logging.info('User not found in cache, retrieving from database.')
						userkey = int(userkeystr)
						user = AskNowUser.get_by_id(userkey)
						logging.info('User retrieved from datavase')
						memcache.set(key, user)
					userdbkey = user.key
					username = user.username	 
				else:
					logging.info('Authentification not successful, resetting cookie and continuing as anonymous user')
					self.reset_cookie('userid')
					auth = False
			else:
				logging.info('Cookie for userid misformatted, resetting cookie and continuing as anonymous user')
				self.reset_cookie('userid')
				auth = False
		else:
			logging.info('Cookie for userid not set, continuing as anonymous user')
			auth = False
		if not auth and not q:
			logging.info('User not authentificated and no question asked, showing plain demo page.')
			self.render('asknowdemo.html')
			return
		if not auth and q:
			logging.info('Anonymous user asked question %s, loading answer' % q)
			answers = []
			answers.append(self.retrieve_answer(q))
			logging.info('Answer loaded, rendering.')
			self.render('asknowdemo_answer.html', answers = answers, q = q)
			return
		# if auth:
		qkey = 'questions-%s' % username
		logging.info('User authentificated, loading former questions from cache.')
		cache = memcache.get(qkey)
		if cache:
			logging.info('Questions found in cache, loading answers')
			questions = cache
		else:
			logging.info('Questions not found in cache, loading from database')
			query = AskNowQuestion.query(AskNowQuestion.userid == userdbkey, distinct=True, projection=[AskNowQuestion.asked, AskNowQuestion.question]).order(-AskNowQuestion.asked)
			query = list(query)
			questions = []
			for res in query:
				questions.append(res.question)
			logging.info('Questions loaded from database.')
		if q:
			questions.insert(0, q)
			new_question = AskNowQuestion(userid = userdbkey, question = q)
			new_question.put()
			logging.info('New question added to list and to database.')
		display_questions = questions[:5]
		memcache.set(qkey, display_questions)
		logging.info('5 most recent questions added to cache, loading answers for questions.')
		answers = []
		for question in display_questions:
			cur_answer = self.retrieve_answer(question)
			if cur_answer:
				answers.append(cur_answer)
				logging.info('Retrieved answer for question "%s"' % question)
		logging.info('Rendering answer page.')
		self.render('asknowdemo_answer.html', answers = answers, q = q)
			
class AskNowJSONAnswerHandler(Handler):
	API_URL = 'https://en.wikipedia.org/w/api.php'

	def retrieve_info(self, title):
		answer = {}
		answer['title'] = title
		req = {}
		req['action'] = 'query'
		req['prop'] = 'info|pageimages|extracts'
		req['titles'] = title
		req['inprop'] = 'url'
		req['piprop'] = 'original'
		req['exintro'] = True
		req['exsectionformat'] = 'raw'
		req['format'] = 'json'
		req['indexpageids'] = True
		params = urllib.urlencode(req)
		url = self.API_URL + '?' + params
		urlobj = urllib.urlopen(url)
		json_data = json.load(urlobj)
		if json_data.get('error'):
			answer['error'] = 3
			answer['message'] = 'Error parsing Wikipedia API: %s' % json_data['error']['info']
			return answer
		pageid = json_data['query']['pageids'][0]
		answer['abstract'] = json_data['query']['pages'][pageid]['extract']
		answer['wplink'] = json_data['query']['pages'][pageid]['fullurl']
		answer['imgsrc'] = json_data['query']['pages'][pageid]['thumbnail']['original']
		return answer
	
	def get(self):
		answers = {
			'who is the president of the united states': 'Barack Obama',
			'who is the president elect of the united states': 'Donald Trump',
			'in which city was beethoven born': 'Bonn',
			'in which city was adenauer born': 'Cologne',
			'what country is shah rukh khan from': 'India'
		}
		query = self.request.get('q')
		question = self.request.get('q')
		question = question.lower().replace('?', '')
		answer = {}
		if not question:
			answer = { 'error': 2, 'message': 'Application needs a q parameter, none given.' }
		if question in answers:
			answer = self.retrieve_info(answers[question])
		else:
			answer = { 'error': 1, 'message': 'AskNow does not know the answer to this question.' }
		answer['question'] = query
		json_string = json.dumps(answer)
		self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
		self.write(json_string)
		
class AskNowLogoutHandler(Handler):
	def get(self):
		self.reset_cookie('userid')
		self.redirect(webapp2.uri_for('demo'))
		
class AskNowSignUpHandler(Handler):
	def render_form(self, values = {}, errors = {}):
		self.render('signup.html', values = values, errors = errors)
	
	def get(self):
		self.render_form()
	
	def post(self):
		username = self.request.get('username')
		password = self.request.get('password')
		verify = self.request.get('verify')
		email = self.request.get('email')
		if re.match('^[a-zA-Z0-9_-]{3,20}$', username) and username:
			valid_username = True
		else:
			valid_username = False
		if re.match('^.{3,20}$', password) and password:
			valid_password = True
		else:
			valid_password = False
		if password == verify:
			valid_verify = True
		else:
			valid_verify = False
		if re.match('^[\S]+@[\S]+.[\S]+$', email) or not email:
			valid_email = True
		else:
			valid_email = False
		query = AskNowUser.query(AskNowUser.username == username)
		if query.count() > 0:
			user_exists = True
		else:
			user_exists = False
		if valid_username and valid_password and valid_verify and valid_email and not user_exists:
			salt = self.generate_salt()
			pwhash = self.generate_pwhash(password, salt)
			newuser = AskNowUser(username = username, password = pwhash, salt = salt, email = email)
			newkey = newuser.put()
			newid = newkey.id()
			self.response.headers.add_header('Set-Cookie', 'userid=%s|%s; Path=/' % (newid, self.hash_str(newid)))
			self.redirect(webapp2.uri_for('demo'))
		else:
			values = {}
			values['username'] = username
			values['email'] = email
			errors = {}
			if not valid_username:
				errors['username'] = 'Invalid username'
			elif user_exists:
				errors['username'] = 'This user exists already'
			if not valid_password:
				errors['password'] = 'Invalid password'
			if not valid_verify:
				errors['verify'] = 'Passwords do not match'
			if not valid_email:
				errors['email'] = 'Invalid email'
			self.render_form(values = values, errors = errors)

class AskNowLoginHandler(Handler):
	def render_form(self, error = ''):
		self.render('login.html', error = error)
	
	def get(self):
		self.render_form()
	
	def post(self):
		username = self.request.get('username')
		password = self.request.get('password')
		query = AskNowUser.query(AskNowUser.username == username)
		user = query.get()
		if username and query.count() > 0:
			pwhash = user.password
			salt = user.salt
			if self.verify_password(pwhash, password, salt):
				userid = user.key.id()
				self.response.headers.add_header('Set-Cookie', 'userid=%s|%s; Path=/' % (userid, self.hash_str(userid)))
				self.redirect(webapp2.uri_for('demo'))
			else:
				self.render_form(error = 'Invalid login')
		else:
			self.render_form(error = 'Invalid login')
		

PATH = '/asknow/'
app = webapp2.WSGIApplication([
    webapp2.Route(PATH + 'demo', handler = AskNowDemoHandler, name = 'demo'),
    (PATH + 'json', AskNowJSONAnswerHandler),
    (PATH + 'signup', AskNowSignUpHandler),
    (PATH + 'login', AskNowLoginHandler),
    (PATH + 'logout', AskNowLogoutHandler),
], debug=True)
