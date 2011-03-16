try:
	import django_qfilters as django_filters
except ImportError:
	import django_filters as project_filters

class ParameterFilterSet(project_filters.FilterSet):
	def get_parameters(self):
		parameters = []
		skip_list = ['submit', 'q', 'o', 'ot', 'p']

		if 'submit' in self.data:
			for h,k in self.data.lists():
				if self.data[h] and not h.lower() in skip_list:
					parameters.append((h,k))

		parameters = sorted(parameters)
		return parameters
