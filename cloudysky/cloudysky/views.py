from django.http import HttpResponse
from datetime import datetime
import pytz

def dummypage(request):
    return HttpResponse("No content here, sorry!")

def app_time(request):
	central = pytz.timezone('America/Chicago')
	now_cdt = datetime.now(central)
	time_str = now_cdt.strftime('%H:%M')
	return HttpResponse(time_str)

def app_sum(request):
	n1 = request.GET.get('n1', '0')
	n2 = request.GET.get('n2', '0')
	result = float(n1) + float(n2)
	return HttpResponse(str(result))
	
	
