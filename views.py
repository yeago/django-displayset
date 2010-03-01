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

	def __init__(self,queryset,request,*args,**kwargs):
		self.filtered_queryset = queryset
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
			full_result_count = self.root_query_set.count()

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

		self.result_count = result_count
		self.full_result_count = full_result_count
		self.result_list = result_list
		self.can_show_all = can_show_all
		self.multi_page = multi_page
		self.paginator = paginator


	def get_ordering(self):
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
	
	def changelist_view(self, request, extra_context=None):
		"The 'change list' admin view for this model."
		from django.contrib.admin.views.main import ERROR_FLAG
		from django.contrib.admin.options import IncorrectLookupParameters
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

		try:
			cl = DisplayList(self.filtered_queryset,request, self.model, list_display, self.list_display_links, self.list_filter,
		self.date_hierarchy, self.search_fields, self.list_select_related, self.list_per_page, self.list_editable, self)
		except IncorrectLookupParameters:
			# Wacky lookup parameters were given, so redirect to the main
			# changelist page, without parameters, and pass an 'invalid=1'
			# parameter via the query string. If wacky parameters were given and
			# the 'invalid=1' parameter was already in the query string, something
			# is screwed up with the database, so display an error page.
			if ERROR_FLAG in request.GET.keys():
				return render_to_response('admin/invalid_setup.html', {'title': 'Database error'})
			return HttpResponseRedirect(request.path + '?' + ERROR_FLAG + '=1')

		#<<<<
		# if auto_redirect is true we should handle that before anything else
		if self.auto_redirect and cl.query_set.count() == 1:
			obj = self.filtered_queryset[0]
			try:
				url = obj.get_absolute_url()
			except AttributeError:
				url = None
			if url: # if no url just go ahead and show the display set normally
				return HttpResponseRedirect(url)
		#<<<<

		# If the request was POSTed, this might be a bulk action or a bulk edit.
		# Try to look up an action first, but if this isn't an action the POST
		# will fall through to the bulk edit check, below.
		if actions and request.method == 'POST':
			response = self.response_action(request, queryset=cl.get_query_set())
			if response:
				return response

		# If we're allowing changelist editing, we need to construct a formset
		# for the changelist given all the fields to be edited. Then we'll
		# use the formset to validate/process POSTed data.
		formset = cl.formset = None

		# Handle POSTed bulk-edit data.
		if request.method == "POST" and self.list_editable:
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

		context = {
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
		}
		context.update(extra_context or {})
		context_instance = RequestContext(request, current_app=self.admin_site.name)
		return render_to_response(self.change_list_template or [
			'admin/%s/%s/change_list.html' % (app_label, opts.object_name.lower()),
			'admin/%s/change_list.html' % app_label,
			'admin/change_list.html'
		], context, context_instance=context_instance)
	
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
	csv_export.short_description = "Export to CSV"
	#<<<<

