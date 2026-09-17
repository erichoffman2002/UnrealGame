"""Lighting and atmosphere.

daylight() applies the whole proven setup in one call. The individual
functions are there when a scene needs something different.

Two settings here were expensive to discover and are easy to get wrong:

* The directional light must be flagged as the atmosphere's sun light, or
  SkyAtmosphere renders a twilight sky no matter how bright the sun is.
* Brightness is controlled by the post-process exposure bias, not by the
  sun's intensity in lux - auto-exposure normalises intensity away.
"""

import unreal

import ue_place
from ue_util import log, rot, safe_set, v


def sun(yaw=-55.0, pitch=-34.0, intensity=100.0, color=(1.0, 0.94, 0.86),
        volumetric_scattering=2.2, shadow_distance=14000.0, label="Sun"):
    """Directional key light, registered as the SkyAtmosphere sun."""
    actor = ue_place.spawn(unreal.DirectionalLight, v(0, 0, 1500),
                           rot(yaw, pitch), label)
    if actor is None:
        return None
    comp = actor.get_component_by_class(unreal.DirectionalLightComponent)
    comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    comp.set_intensity(float(intensity))
    comp.set_light_color(unreal.LinearColor(color[0], color[1], color[2], 1.0))
    # Without these the sky renders as dusk regardless of sun intensity.
    safe_set(comp, "atmosphere_sun_light", True)
    safe_set(comp, "atmosphere_sun_light_index", 0)
    safe_set(comp, "volumetric_scattering_intensity", volumetric_scattering)
    safe_set(comp, "dynamic_shadow_distance_movable_light", shadow_distance)
    safe_set(comp, "cascade_distribution_exponent", 2.4)
    return actor


def sky_light(intensity=7.0, volumetric_scattering=1.6, label="SkyLight"):
    """Ambient fill. Without a decent sky light, shadows crush to black -
    scene captures in particular resolve no Lumen GI to fill them."""
    actor = ue_place.spawn(unreal.SkyLight, v(0, 0, 900), rot(0.0), label)
    if actor is None:
        return None
    comp = actor.get_component_by_class(unreal.SkyLightComponent)
    comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    comp.set_intensity(float(intensity))
    safe_set(comp, "real_time_capture", True)
    safe_set(comp, "volumetric_scattering_intensity", volumetric_scattering)
    return actor


def sky_atmosphere(label="SkyAtmosphere"):
    return ue_place.spawn(unreal.SkyAtmosphere, v(0, 0, 0), rot(0.0), label)


def height_fog(density=0.045, falloff=0.08, start_distance=1500.0,
               inscattering=(0.42, 0.40, 0.36), volumetric=True,
               volumetric_distance=9000.0, label="HeightFog"):
    """Exponential height fog. Also the cheapest way to hide the far edge of a
    finite ground plane, which otherwise meets the sky in a hard line."""
    actor = ue_place.spawn(unreal.ExponentialHeightFog, v(0, 0, 200),
                           rot(0.0), label)
    if actor is None:
        return None
    comp = actor.get_component_by_class(unreal.ExponentialHeightFogComponent)
    safe_set(comp, "fog_density", density)
    safe_set(comp, "fog_height_falloff", falloff)
    safe_set(comp, "start_distance", start_distance)
    safe_set(comp, "fog_inscattering_luminance",
             unreal.LinearColor(inscattering[0], inscattering[1],
                                inscattering[2], 1.0))
    safe_set(comp, "enable_volumetric_fog", bool(volumetric))
    safe_set(comp, "volumetric_fog_scattering_distribution", 0.55)
    safe_set(comp, "volumetric_fog_extinction_scale", 1.0)
    safe_set(comp, "volumetric_fog_distance", volumetric_distance)
    return actor


def post_process(exposure_bias=2.5, bloom=0.55, vignette=0.22,
                 highlight_gain=(1.06, 1.01, 0.92),
                 shadow_gain=(0.93, 0.97, 1.09), film_slope=0.92,
                 label="PostProcess"):
    """Unbound post-process volume.

    exposure_bias is the brightness control. Do not lock auto-exposure with
    matching min/max brightness - that reads as night.
    """
    ppv = ue_place.spawn(unreal.PostProcessVolume, v(0, 0, 0), rot(0.0), label)
    if ppv is None:
        return None
    safe_set(ppv, "unbound", True)

    settings = ppv.get_editor_property("settings")
    safe_set(settings, "override_auto_exposure_bias", True)
    safe_set(settings, "auto_exposure_bias", float(exposure_bias))
    safe_set(settings, "override_bloom_intensity", True)
    safe_set(settings, "bloom_intensity", float(bloom))
    safe_set(settings, "override_vignette_intensity", True)
    safe_set(settings, "vignette_intensity", float(vignette))
    safe_set(settings, "override_color_gain_highlights", True)
    safe_set(settings, "color_gain_highlights",
             unreal.Vector4(highlight_gain[0], highlight_gain[1],
                            highlight_gain[2], 1.0))
    safe_set(settings, "override_color_gain_shadows", True)
    safe_set(settings, "color_gain_shadows",
             unreal.Vector4(shadow_gain[0], shadow_gain[1], shadow_gain[2], 1.0))
    safe_set(settings, "override_film_slope", True)
    safe_set(settings, "film_slope", float(film_slope))
    ppv.set_editor_property("settings", settings)
    return ppv


def daylight(sun_yaw=-55.0, sun_pitch=-34.0, sun_intensity=100.0,
             sky_intensity=7.0, fog_density=0.045, exposure_bias=2.5):
    """Sun + sky light + atmosphere + fog + post process, in one call.

    These are the values the ruin scene was tuned to; override as needed.
    """
    result = {
        "sun": sun(yaw=sun_yaw, pitch=sun_pitch, intensity=sun_intensity),
        "sky_light": sky_light(intensity=sky_intensity),
        "atmosphere": sky_atmosphere(),
        "fog": height_fog(density=fog_density),
        "post_process": post_process(exposure_bias=exposure_bias),
    }
    log("lighting: sun, sky light, atmosphere, fog, post process")
    return result
