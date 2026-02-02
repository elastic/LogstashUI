from django.shortcuts import render

# Create your views here.
def GrokDebugger(request):
    return render(request, 'grok_debugger.html')
