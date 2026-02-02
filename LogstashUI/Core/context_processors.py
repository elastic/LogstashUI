from .version_checker import check_for_update


def version_update_info(request):
    """
    Context processor to add version update information to all templates.
    """
    update_info = check_for_update()
    return {
        'version_update': update_info
    }
