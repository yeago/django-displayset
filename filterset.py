try: 
	import django_qfilters as django_filters
	# See https://github.com/subsume/django_qfilters
except ImportError:
	import django_filters

class ParameterFilterSet(django_filters.FilterSet):
	def get_parameters(self):
		parameters = []
		skip_list = ['submit', 'q', 'o', 'ot', 'p']

		if 'submit' in self.data:
			for h,k in self.data.lists():
				if self.data[h] and not h.lower() in skip_list:
					parameters.append((h,k))

		parameters = sorted(parameters)
		return parameters

