"""Keep inspector blur and separately added Gaussian Blur mutually exclusive."""

def external_blur(item):
    return any(e.get('name')=='Gaussian Blur' and not e.get('inspector_background_blur') for e in item.effects)


def inspector_enabled(item):
    return any(e.get('inspector_background_blur') and e.get('enabled',True) for e in item.effects)


def conflicts(item,effect):
    return bool(effect.get('name')=='Gaussian Blur' and
                (external_blur(item) if effect.get('inspector_background_blur') else inspector_enabled(item)))
