import operator
import csv

from HTMLParser import HTMLParser

from django import forms
from django import template
from django.core.exceptions import PermissionDenied
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin import options as adminoptions
from django.contrib.admin import helpers
from django.contrib.admin.views.main import ERROR_FLAG
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.core.paginator import Paginator, InvalidPage
from django.db.models import Q
from django.db import models
from django.http import HttpResponseRedirect,HttpResponse
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.http import urlencode
from django.utils.translation import ungettext
from django.utils.encoding import force_unicode
from django.utils.functional import update_wrapper
from django.views.decorators.csrf import csrf_protect

class HTMLRemover(HTMLParser):
	def __init__(self):
		self.reset()
		self.fed = []
	def handle_data(self, d):
		self.fed.append(d)
	def get_data(self):
		return ''.join(self.fed)

def cap_first(string):
	#This works exactly like string.title(), except it does not remove interior capitalization.
	if string:
		if string == None or string == "":
			return string
		string = "%s%s" % (string[0].upper(), string[1:])
		seperators = (" ", "-", "_", "/", "\\",)
		for i, char in enumerate(string):
			if char in seperators and i+1 < len(string):
				string = "%s%s%s" % (string[0:i+1], string[i+1].upper(), string[i+2:])
		return string
	return None

def pretty(string):
	if string:
		if string[0] == "_":
			string = "%s%s" % (" ", string[1:])
		for i, char in enumerate(string):
			if char == "_":
				string = "%s%s%s" % (string[0:i], " ", string[i+1:])
		return cap_first(string.strip())
	return None

class DefaultDisplaySite(object):
	actions = []
	root_path = '/'
	name = 'Default DisplaySet Site'
	_registry = {}

	def admin_view(self,view):
		def no_wrap(request,*args,**kwargs):
			return view(request,*args,**kwargs)
			no_wrap = csrf_protect(no_wrap)
		return update_wrapper(no_wrap, view)

def generic(request,queryset,display_class,extra_context=None,display_site=DefaultDisplaySite):
	display = display_class(queryset,display_site)
	return display.changelist_view(request,extra_context)

def filterset_generic(request,filter,display_class,queryset=None,extra_context=None,display_site=DefaultDisplaySite):
	"""
	In this situation, we're using the FilterSet which has the convenience get_parameters()
	which gives us a nicely formatted result of what is being queried upon.

	It supplies extra context which can be used to create a table report_header in the template
	"""
	queryset = queryset or filter.qs
	extra_context = extra_context or {}
	display = display_class(queryset,display_site)

	if hasattr(filter,'get_parameters'):
		params = filter.get_parameters()
	else:
		params =  []

	form = filter.form

	updated_params = []
	for field,value in params:

		new_value = value

		if hasattr(display,"parameter_fields") and display.parameter_fields.get(field,None):
			new_value = display.parameter_fields.get(field)(form,field,value)
		elif form and field in form.fields:

			if getattr(form.fields[field],'queryset',None):
				selected_set = form.fields[field].queryset.filter(pk__in=value)
				new_value = ', '.join([form.fields[field].label_from_instance(o) for o in selected_set])
			elif getattr(form.fields[field],'choices', None):
				new_value = ', '.join([unicode(c[1]) for c in form.fields[field].choices if unicode(c[0]) in value])
			else:
				new_value = ', '.join(new_value)

		if new_value is not None:
			updated_params.append((pretty(field),new_value))

	if params:
		#Here, we gather all the range fields and display them as one parameter
		range_dict = {}
		#First, compare the names to see which fields belong together
		for i,p in enumerate(updated_params):
			param_name = p[0][:-1]
			for j in range(i+1,len(updated_params)-1):
				param_name_check = updated_params[j][0][:-1]
				if param_name == param_name_check:
					if not param_name in range_dict:
						range_dict[param_name] = [i]
					if j not in range_dict[param_name]:
						range_dict[param_name].append(j)
		# Append the new range values to the updated_parameters
		for field,values in range_dict.items():
			field_name = field[:-1]
			field_values = ' - '.join([updated_params[v][1][0] for v in values])
			updated_params.append((field_name,field_values))
		# Remove the old parameters from updated_parameters
		remove_indices = []
		[remove_indices.extend(v) for v in range_dict.values()]
		for i, index in enumerate(sorted(remove_indices)):
			del updated_params[index-i]

	if updated_params:
		if not extra_context.get('report_header'):
			extra_context['report_header'] = []

		extra_context['report_header'].extend(updated_params)

	extra_context.update({'filter': filter})

	return display.changelist_view(request,extra_context)

class ColumnsForm(forms.Form):
	columns = forms.MultipleChoiceField(required=False,widget=FilteredSelectMultiple("Columns",is_stacked=False))

def list_replace(replacements, original): # replacements are [(index,function),(index,function),...]
	for item in replacements: # item is (index, function)
		original.pop(item[0])
		original.insert(item[0],item[1])
	return original

# How to add csv export to your own display set
# class DisplaySetSubclass(DisplaySet):
#	export = True
#	export_name = "display_report" ####makes the file name display_report.csv
def csv_export(modeladmin, request, queryset):
	response = HttpResponse(mimetype='text/csv')
	try:
		export_name = modeladmin.export_name
	except AttributeError:
		export_name = queryset.model._meta.verbose_name
	finally:
		response['Content-Disposition'] = 'attachment; filename=%s.csv' % export_name
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
					header.append(f.func_name)
				continue
			fields.append(f)
			header.append(f)
	writer.writerow(header)
	for obj in queryset:
		row = []
		for f in fields:
			if f != 'action_checkbox':
				text = ""
				if callable(f):
					text = str(f(obj))
					htmlremover = HTMLRemover()
					htmlremover.feed(text)
					text = htmlremover.get_data()
				else:
					text = getattr(obj, f, "(None)")
				row.append(text)
		writer.writerow(row)
	return response
csv_export.short_description = "Export to Excel"

ORDER_VAR = 'o'
ORDER_TYPE_VAR = 'ot'
MAX_SHOW_ALL = 1000
class DisplayList(ChangeList):

	def __init__(self,request,*args,**kwargs):

		self.list_display_links = [None]
		super(DisplayList,self).__init__(request,*args,**kwargs)

		if hasattr(self.model_admin,'list_display_default') and '__str__' in self.model_admin.list_display:
			# Remove the Django default display if a new default has been established with the API
			self.model_admin.list_display.remove('__str__')

		self.multiple_params_safe = dict(request.GET.lists())
		self.model_admin.list_display_default = self.handle_default_display()
		self.list_display_options = self.handle_possible_list_display()
		self.list_display = self.handle_list_display(request)
		self.order_field, self.order_type = self.get_ordering()
		self.query_set = self.get_query_set()
		self.get_results(request)

		if not self.model_admin.actions:
			try:
				self.list_display.remove('action_checkbox')
			except ValueError:
				pass

	def get_query_string(self, new_params=None, remove=None):
		if new_params is None: new_params = {}
		if remove is None: remove = []
		final_params = []
		p = self.multiple_params_safe.copy()
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

	#<<<<

	def get_results(self, request):
		paginator = Paginator(self.query_set, self.list_per_page)
		# Get the number of objects, with admin filters applied.
		result_count = paginator.count

		# Get the total number of objects, with no admin filters applied.
		# Perform a slight optimization: Check to see whether any filters were
		# given. If not, use paginator.hits to calculate the number of objects,
		# because we've already done paginator.hits and the value is cached.
		if not self.query_set.query.where:
			full_result_count = result_count
		else:
			#<<<<

			#Temporary fix... we are going to patch this...
			#The template has also been temp fixed to not show this number
			full_result_count = -1#self.root_query_set.count()

			#<<<

		can_show_all = MAX_SHOW_ALL #<<<<
		multi_page = result_count > self.list_per_page

		# Get the list of objects to display on this page.
		if (self.show_all and can_show_all) or not multi_page:
			result_list = self.query_set._clone()
		else:
			try:
				result_list = paginator.page(self.page_num+1).object_list
			except InvalidPage:
				result_list = ()

		if getattr(self,"after_pagination_select_related",[]):
			result_list = result_list.select_related(*self.after_pagination_select_related)

		self.result_count = result_count
		self.full_result_count = full_result_count
		self.result_list = result_list
		self.can_show_all = can_show_all
		self.multi_page = multi_page
		self.paginator = paginator

	def handle_default_display(self):
		replace_list = []
		for x,f in enumerate(self.model_admin.list_display_default):
			func = self.get_absolute_urlify(f)
			if func:
				replace_list.append((x,func))

		return list_replace(replace_list,self.model_admin.list_display_default)

	def handle_possible_list_display(self):
		if not hasattr(self.model_admin,"list_display_options"):
			self.model_admin.list_display_options = self.model_admin.list_display
			options = self.model_admin.list_display_options

		else:
			# incase there are duplicate options, we uniquify
			options = set(self.model_admin.list_display).union(self.model_admin.list_display_options)
		
		options = list(options) # Make a copy of the list

		if helpers.ACTION_CHECKBOX_NAME in options:
			options.remove(helpers.ACTION_CHECKBOX_NAME)

		replace_list = []
		for x,f in enumerate(set(options).difference(self.model_admin.list_display_default)):
			func = self.get_absolute_urlify(f)
			if func:
				replace_list.append((x,func))

		return list_replace(replace_list,options)

	def handle_list_display(self, request):

		replace_list = []

		if request.GET.getlist('columns'):
			modified_list_display = []
			for column in request.GET.getlist('columns'):
				if column in self.list_display_options:
					modified_list_display.append(column)
				else:
					try:
						index = [getattr(i,"func_name",None) for i in self.list_display_options].index(column)
						modified_list_display.append(self.list_display_options[index])
					except ValueError,IndexError:
						pass

			if 'action_checkbox' in self.model_admin.list_display:
				self.model_admin.list_display = ['action_checkbox'] + modified_list_display
			else:
				self.model_admin.list_display = modified_list_display
		
		self.model_admin.list_display = self.prepend_default_display()

		return self.model_admin.list_display

	def prepend_default_display(self):
		list_display = self.model_admin.list_display[:]
		for f in reversed(self.model_admin.list_display_default):
			if f not in list_display:
				if 'action_checkbox' in list_display:
					list_display.insert(1,f) # action checkbox is in the first slot
				else:
					list_display.insert(0,f)
		return list_display

	def get_absolute_urlify(self,field):

		func = None
		if field in self.model_admin.use_get_absolute_url:
			func = lambda obj: "<a href=\"%s\">%s</a>" % (obj.get_absolute_url(), getattr(obj,func.field)) # or func.field
			func.admin_order_field = field
			func.short_description = pretty(field)
			func.func_name = field # Otherwise the func_name is '<lambda>'
		elif callable(field) and field.func_name in self.model_admin.use_get_absolute_url:
			func = lambda obj: "<a href=\"%s\">%s</a>" % (obj.get_absolute_url(), func.field(obj)) # or func.field(obj)
			try:
				func.admin_order_field = field.admin_order_field
			except AttributeError:
				func.admin_order_field = None
			try:
				func.short_description = field.short_description
			except AttributeError:
				func.short_description = pretty(field.func_name)
			func.func_name = field.func_name # Otherwise the func_name is '<lambda>'

		if func:
			func.allow_tags = True
			func.field = field
			return func
		return None

class DisplaySet(adminoptions.ModelAdmin):
	change_list_template = 'displayset/base.html'
	use_get_absolute_url = []
	list_display_default = [] 
	use_default_links = False # Set this to true to re-enable the Django automatic links
	after_pagination_select_related = []
	auto_redirect = False
	auto_redirect_url = None
	export = False
	export_name = None
	distinct = False

	def __init__(self,queryset,display_set_site,*args,**kwargs):

		self.filtered_queryset = queryset
		if self.export:
			self.actions.append(csv_export)
		if self.list_display != None:
			self.list_display = list(self.list_display)

		if not self.list_display_links and not self.use_default_links:
			"""
			This removes the default behavior of the ModelAdmin, which
			tries to place a link on the first column by default
			"""
			self.list_display_links = [None]

		super(DisplaySet,self).__init__(queryset.model,display_set_site)

		if not self.actions and 'action_checkbox' in self.list_display:
			self.list_display.remove('action_checkbox')

	def get_changelist(self,request):
		DisplayList.filtered_queryset = self.filtered_queryset
		DisplayList.after_pagination_select_related = self.after_pagination_select_related
		return DisplayList

	def queryset(self, request):
		if self.distinct:
			return self.filtered_queryset.distinct()
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

	def changelist_view(self, request, extra_context=None):
		"The 'change list' admin view for this model."
		opts = self.model._meta
		app_label = opts.app_label

		# Check actions to see if any are available on this changelist
		actions = self.get_actions(request)

		# Remove action checkboxes if there aren't any actions available.
		list_display = list(self.list_display)
		if not actions:
			try:
				list_display.remove('action_checkbox')
			except ValueError:
				pass

		ChangeList = self.get_changelist(request)
		try:
			cl = ChangeList(request, self.model, list_display, self.list_display_links, self.list_filter,
				self.date_hierarchy, self.search_fields, self.list_select_related, self.list_per_page, self.list_editable, self)
		except adminoptions.IncorrectLookupParameters:
			# Wacky lookup parameters were given, so redirect to the main
			# changelist page, without parameters, and pass an 'invalid=1'
			# parameter via the query string. If wacky parameters were given
			# and the 'invalid=1' parameter was already in the query string,
			# something is screwed up with the database, so display an error
			# page.
			if ERROR_FLAG in request.GET.keys():
				return render_to_response('admin/invalid_setup.html', {'title': ('Database error')})
			return HttpResponseRedirect(request.path + '?' + ERROR_FLAG + '=1')
		
		# if auto_redirect is true we should handle that before anything else
		if self.auto_redirect and cl.query_set.count() == 1:

			obj = cl.query_set[0]
			try:
				url = obj.get_absolute_url()
			except AttributeError:
				url = None

			if url: # if no url just go ahead and show the display set normally
				return HttpResponseRedirect(url)

		# If the request was POSTed, this might be a bulk action or a bulk
		# edit. Try to look up an action or confirmation first, but if this
		# isn't an action the POST will fall through to the bulk edit check,
		# below.
		action_failed = False
		selected = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)

		# Actions with no confirmation
		if actions and request.method == 'POST':
			response = self.response_action(request, queryset=cl.get_query_set())
			if response:
				return response

		# If we're allowing changelist editing, we need to construct a formset
		# for the changelist given all the fields to be edited. Then we'll
		# use the formset to validate/process POSTed data.
		formset = cl.formset = None

		# Handle POSTed bulk-edit data.
		if (request.method == "POST" and self.list_editable and
				'_save' in request.POST and not action_failed):
			FormSet = self.get_changelist_formset(request)
			formset = cl.formset = FormSet(request.POST, request.FILES, queryset=cl.result_list)
			if formset.is_valid():
				changecount = 0
				for form in formset.forms:
					if form.has_changed():
						obj = self.save_form(request, form, change=True)
						self.save_model(request, obj, form, change=True)
						form.save_m2m()
						change_msg = self.construct_change_message(request, form, None)
						self.log_change(request, obj, change_msg)
						changecount += 1

				if changecount:
					if changecount == 1:
						name = force_unicode(opts.verbose_name)
					else:
						name = force_unicode(opts.verbose_name_plural)
					msg = ungettext("%(count)s %(name)s was changed successfully.",
									"%(count)s %(name)s were changed successfully.",
									changecount) % {'count': changecount,
													'name': name,
													'obj': force_unicode(obj)}
					self.message_user(request, msg)

				return HttpResponseRedirect(request.get_full_path())

		# Handle GET -- construct a formset for display.
		elif self.list_editable:
			FormSet = self.get_changelist_formset(request)
			formset = cl.formset = FormSet(queryset=cl.result_list)

		# Build the list of media to be used by the formset.
		if formset:
			media = self.media + formset.media
		else:
			media = self.media

		# Build the action form and populate it with available actions.
		if actions:
			action_form = self.action_form(auto_id=None)
			action_form.fields['action'].choices = self.get_action_choices(request)
		else:
			action_form = None

		# Build the columns form
		column_form_choices = []
		column_form_initial = []
		default_display = getattr(cl.model_admin, "list_display_default", [])

		for item in cl.list_display + cl.list_display_options:

			if item in default_display or item == 'action_checkbox':
				continue
	
			name = getattr(item,"func_name",item)
		
			display_name = getattr(item,"short_description",pretty(name))

			if not (name,display_name) in column_form_choices:
				column_form_choices.append((name,display_name))

			if item in cl.list_display:
				column_form_initial.append(name)

		columns_form = ColumnsForm(request.GET or None)
		columns_form.fields['columns'].choices = column_form_choices
		columns_form.fields['columns'].initial = column_form_initial

		context = {
			'module_name': force_unicode(opts.verbose_name_plural),
			'columns_form': columns_form,
			'title': cl.title,
			'is_popup': cl.is_popup,
			'cl': cl,
			'media': media,
			'has_add_permission': self.has_add_permission(request),
			'root_path': self.admin_site.root_path,
			'app_label': app_label,
			'action_form': action_form,
			'actions_on_top': self.actions_on_top,
			'actions_on_bottom': self.actions_on_bottom,
			'actions_selection_counter': self.actions_selection_counter,
		}
		context.update(extra_context or {})
		context_instance = template.RequestContext(request, current_app=self.admin_site.name)
		return render_to_response(self.change_list_template or [
			'admin/%s/%s/change_list.html' % (app_label, opts.object_name.lower()),
			'admin/%s/change_list.html' % app_label,
			'admin/change_list.html'
		], context, context_instance=context_instance)

