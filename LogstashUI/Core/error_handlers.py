"""
Custom error handlers for LogstashUI
All errors use a single template with different context
"""
import sys
import traceback
from django.shortcuts import render


def handler400(request, exception=None):
    return render(request, 'error.html', {
        'error_code': '400',
        'error_title': 'Bad Request',
        'error_message': 'The server could not understand your request.',
        'exception': str(exception) if exception else None,
    }, status=400)


def handler403(request, exception=None):
    return render(request, 'error.html', {
        'error_code': '403',
        'error_title': 'Access Denied',
        'error_message': 'You do not have permission to access this resource.',
        'exception': str(exception) if exception else None,
    }, status=403)


def handler404(request, exception=None):
    return render(request, 'error.html', {
        'error_code': '404',
        'error_title': 'Page Not Found',
        'error_message': 'The page you are looking for does not exist.',
        'exception': str(exception) if exception else None,
        'path': request.path,
    }, status=404)


def handler500(request):
    # Capture the current exception info
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type:
        stack_trace = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    else:
        stack_trace = None
    
    return render(request, 'error.html', {
        'error_code': '500',
        'error_title': 'Server Error',
        'error_message': 'Something went wrong on our end. Please try again later.',
        'exception': str(exc_value) if exc_value else None,
        'stack_trace': stack_trace,
    }, status=500)
