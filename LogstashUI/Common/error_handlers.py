#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render


def handler400(request, exception=None):
    return render(request, 'error.html', {
        'error_code': '400',
        'error_title': 'Bad Request',
        'error_message': 'The server could not understand your request.',
        'exception': exception.__class__.__name__ if exception else None,
    }, status=400)


def handler403(request, exception=None):
    return render(request, 'error.html', {
        'error_code': '403',
        'error_title': 'Access Denied',
        'error_message': 'You do not have permission to access this resource.',
        'exception': exception.__class__.__name__ if exception else None,
    }, status=403)


def handler404(request, exception=None):
    return render(request, 'error.html', {
        'error_code': '404',
        'error_title': 'Page Not Found',
        'error_message': 'The page you are looking for does not exist.',
        'exception': exception.__class__.__name__ if exception else None,
        'path': request.path,
    }, status=404)


def handler500(request, exception=None):

    return render(request, 'error.html', {
        'error_code': '500',
        'error_title': 'Server Error',
        'error_message': 'Something went wrong on our end!',
        'exception': exception.__class__.__name__ if exception else None,
        'path': request.path
    }, status=500)
