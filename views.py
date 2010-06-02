import operator
import csv

from django.core.exceptions import PermissionDenied
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin import options as adminoptions
from django.core.paginator import Paginator, InvalidPage
from django.http import HttpResponseRedirect,HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.http import urlencode
from django.db.models import Q
from django.db import models
from django.contrib.admin import helpers

class DefaultDisplaySite(object):
	actions = []
	root_path = '/'
	name = 'Default DisplaySet Site' 
	
	def admin_view(self,view):
		def no_wrap(request,*args,**kwargs):
			return view(request,*args,**kwargs)
		from django.views.decorators.csrf import csrf_protect
		from django.utils.functional import update_wrapper
		no_wrap = csrf_protect(no_wrap)
		return update_wrapper(no_wrap, view)

def generic(request,queryset,display_class,extra_context=None,display_site=DefaultDisplaySite):
	return display_class(queryset,display_site).changelist_view(request,extra_context)

def list_replace(replacements, original): # replacements are [(index,function),(index,function),...]
	for item in replacements: # item is (index, function)
		original.pop(item[0])
		original.insert(item[0],item[1])
	return original

ORDER_VAR = 'o'
ORDER_TYPE_VAR = 'ot'
MAX_SHOW_ALL = 1000
class DisplayList(ChangeList):
	def __init__(self,request,*args,**kwargs):
		super(DisplayList,self).__init__(request,*args,**kwargs)
		self.multiple_params_safe = dict(request.GET.lists()) #<<<<
	
	def get_query_string(self, new_params=None, remove=None):
		if new_params is None: new_params = {}
		if remove is None: remove = []
		final_params = []
		p = self.multiple_params_safe.copy() #<<<<
		for r in remove:
			for k in p.keys():
				if k.startswith(r):
					del p[k]
		for k, v in new_params.items():
			if v is None:
				if k in p:
					del p[k]
			else:
				p[k] = v
		#<<<<
		for k,v in p.items():
			if isinstance(v, (list,tuple)): 
				if len(v) == 1:
					final_params.append((k,v[0]))
				else:
					final_params.extend([(k, list_value) for list_value in v])
			else:
				final_params.append((k,v))
		#<<<<
		return '?%s' % urlencode(final_params)

	"""
	def get_ordering(self):
		print super(DisplayList,self).get_ordering()
		lookup_opts, params = self.lookup_opts, self.params
		# For ordering, first check the "ordering" parameter in the admin
		# options, then check the object's default ordering. If neither of
		# those exist, order descending by ID by default. Finally, look for
		# manually-specified ordering from the query string.
		ordering = self.model_admin.ordering or lookup_opts.ordering or ['-' + lookup_opts.pk.name]

		if ordering[0].startswith('-'):
			order_field, order_type = ordering[0][1:], 'desc'
		else:
			order_field, order_type = ordering[0], 'asc'
		if ORDER_VAR in params:
			try:
				field_name = self.list_display[int(params[ORDER_VAR])]
				try:
					f = lookup_opts.get_field(field_name)
				except models.FieldDoesNotExist:
					# See whether field_name is a name of a non-field
					# that allows sorting.
					try:
						if callable(field_name):
							attr = field_name
						elif hasattr(self.model_admin, field_name):
							attr = getattr(self.model_admin, field_name)
						else:
							attr = getattr(self.model, field_name)
						order_field = attr.admin_order_field
					except AttributeError:
						if field_name in self.filtered_queryset.query.aggregates or field_name in self.filtered_queryset.query.extra: #<<<<
							order_field = field_name
				else:
					order_field = f.name
			except (IndexError, ValueError):
				pass # Invalid ordering specified. Just use the default.
		if ORDER_TYPE_VAR in params and params[ORDER_TYPE_VAR] in ('asc', 'desc'):
			order_type = params[ORDER_TYPE_VAR]
		return order_field, order_type
	"""

	def get_query_set(self):
		# Set ordering.
		if self.order_field:
			self.filtered_queryset = self.filtered_queryset.order_by('%s%s' % ((self.order_type == 'desc' and '-' or ''), self.order_field))

		# Apply keyword searches.
		def construct_search(field_name):
			if field_name.startswith('^'):
				return "%s__istartswith" % field_name[1:]
			elif field_name.startswith('='):
				return "%s__iexact" % field_name[1:]
			elif field_name.startswith('@'):
				return "%s__search" % field_name[1:]
			else:
				return "%s__icontains" % field_name

		if self.search_fields and self.query:
			for bit in self.query.split():
				or_queries = [Q(**{construct_search(str(field_name)): bit}) for field_name in self.search_fields]
				self.filtered_queryset = self.filtered_queryset.filter(reduce(operator.or_, or_queries))
			for field_name in self.search_fields:
				if '__' in field_name:
					self.filtered_queryset = self.filtered_queryset.distinct()
					break

		return self.filtered_queryset

class DisplaySet(adminoptions.ModelAdmin):
	#<<<<
	change_list_template = 'displayset/base.html'
	use_get_absolute_url = [] 
	default_list_display = [] 
	auto_redirect = False
	auto_redirect_url = None
	export = False
	export_name = None
	def get_changelist(self,request):
		DisplayList.filtered_queryset = self.filtered_queryset
		return DisplayList
	#<<<<

	#<<<<
	def __init__(self,queryset,display_set_site,*args,**kwargs):
		self.filtered_queryset = queryset
		super(DisplaySet,self).__init__(queryset.model,display_set_site)
		self.default_list_display = self.handle_default_display() 
		self.list_display = self.handle_list_display()
		self.add_action_export()		
	#<<<<
		
	#<<<<
	def handle_default_display(self):
		replace_list = []
		for x,f in enumerate(self.default_list_display):
			func = self.get_absolute_urlify(f)
			if func:
				replace_list.append((x,func))
		return list_replace(replace_list,self.default_list_display)

	def handle_list_display(self):
		replace_list = []
		for x,f in enumerate(self.list_display):
			func = self.get_absolute_urlify(f)
			if func:
				replace_list.append((x,func))

		self.list_display = self.prepend_default_display()
		return list_replace(replace_list,self.list_display)
	
	def prepend_default_display(self):
		list_display = self.list_display[:]
		for f in reversed(self.default_list_display):
			if list_display[0] == 'action_checkbox': 
				list_display.insert(1,f) # action checkbox is in the first slot
			else: list_display.insert(0,f)
		return list_display

	def get_absolute_urlify(self,field):
		func = None
		if field in self.use_get_absolute_url:
			func = lambda obj: "<a href='%s'>%s</a>" % (obj.get_absolute_url(), getattr(obj,func.field)) # or func.field
			func.admin_order_field = field
			func.short_description = field
		elif callable(field) and field.__name__ in self.use_get_absolute_url:
			func = lambda obj: "<a href='%s'>%s</a>" % (obj.get_absolute_url, func.field(obj)) # or func.field(obj)
			try:
				func.admin_order_field = field.admin_order_field
			except AttributeError:
				func.admin_order_field = None
			try:
				func.short_description = field.short_description
			except AttributeError:
				func.short_description = field.__name__
		
		if func:
			func.allow_tags = True
			func.field = field
			return func
		return None
	#<<<<
	
	def queryset(self, request):
		return self.filtered_queryset
	
	def response_action(self, request, queryset):
		"""
		Handle an admin action. This is called if a request is POSTed to the
		changelist; it returns an HttpResponse if the action was handled, and
		None otherwise.
		"""
		# There can be multiple action forms on the page (at the top
		# and bottom of the change list, for example). Get the action
		# whose button was pushed.
		try:
			action_index = int(request.POST.get('index', 0))
		except ValueError:
			action_index = 0

		# Construct the action form.
		data = request.POST.copy()
		data.pop(helpers.ACTION_CHECKBOX_NAME, None)
		data.pop("index", None)

		# Use the action whose button was pushed
		try:
			data.update({'action': data.getlist('action')[action_index]})
		except IndexError:
			# If we didn't get an action from the chosen form that's invalid
			# POST data, so by deleting action it'll fail the validation check
			# below. So no need to do anything here
			pass

		action_form = self.action_form(data, auto_id=None)
		action_form.fields['action'].choices = self.get_action_choices(request)

		# If the form's valid we can handle the action.
		if action_form.is_valid():
			action = action_form.cleaned_data['action']
			select_across = action_form.cleaned_data.get('select_across',None)
			func, name, description = self.get_actions(request)[action]

			# Get the list of selected PKs. If nothing's selected, we can't
			# perform an action on it, so bail. Except we want to perform
			# the action explicitely on all objects.

			### We change the default action of returning none as if we want to try returning all <<<<
			"""
			if not selected and not select_across:
				# Reminder that something needs to be selected or nothing will happen
				msg = _("Items must be selected in order to perform actions on them. No items have been changed.")
				self.message_user(request, msg)
				return None

			"""
			selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
			if not select_across and selected:
				# Perform the action only on the selected objects
				queryset = queryset.filter(pk__in=selected)

			response = func(self, request, queryset)

			# Actions may return an HttpResponse, which will be used as the
			# response from the POST. If not, we'll be a good little HTTP
			# citizen and redirect back to the changelist page.
			if isinstance(response, HttpResponse):
				return response
			else:
				return HttpResponseRedirect(".")
		else:
			msg = "No action selected."
			self.message_user(request, msg)

	#<<<<
	# How to add csv export to your own display set
	# class DisplaySetSubclass(DisplaySet):
	#	export = True
	#	export_name = "display_report" ####makes the file name display_report.csv

	def add_action_export(self):
		if self.export == True:
			self.actions.append(self.csv_export)

	def csv_export(self, modeladmin, request, queryset):
		import re
		html_re = re.compile("<.*>(.*)</.*>")
		response = HttpResponse(mimetype='text/csv')
		response['Content-Disposition'] = 'attachment; filename=%s.csv' % (self.export_name or queryset.model)
		writer = csv.writer(response)
		fields = []
		header = []
		for f in modeladmin.list_display:
			if f != 'action_checkbox':
				if callable(f):
					fields.append(f)
					try:
						header.append(f.short_description)
					except AttributeError:
						header.append(f.__name__)
					continue
				fields.append(f);header.append(f)
		writer.writerow(header)
		for obj in queryset:
			row = []
			for f in fields:
				if f != 'action_checkbox':
					if callable(f):
						text = f(obj)
						try:
							text = html_re.search(text).groups()[0]
							row.append(text)
						except (TypeError,AttributeError): # either we got something like a datetime or no match was found (no html, so its clean)
							row.append(text)
						continue
					row.append(getattr(obj, f))
			writer.writerow(row)
		return response
	csv_export.short_description = "Export to Excel"
	#<<<<

