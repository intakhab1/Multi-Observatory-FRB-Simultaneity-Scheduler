import warnings
from astropy.time.core import TimeDeltaMissingUnitWarning
from astropy.coordinates import NonRotationTransformationWarning

warnings.filterwarnings(
    "ignore",
    category=TimeDeltaMissingUnitWarning
)

warnings.filterwarnings(
    "ignore",
    category=NonRotationTransformationWarning
)

warnings.filterwarnings(
    "ignore",
    message="no explicit representation of timezones available for np.datetime64"
)


import json
import csv
from datetime import datetime, timedelta
import numpy as np
import io
import base64

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.lines import Line2D 

from astropy.time import Time, TimeDelta
import astropy.units as u
from astropy.coordinates import SkyCoord, AltAz, get_sun, get_body, EarthLocation
from astroplan import Observer, FixedTarget
from astroplan.plots import plot_airmass
from astroplan.moon import moon_illumination 

from zoneinfo import ZoneInfo

GTC_LOCATION = EarthLocation(
    lon=-17.889 * u.deg,
    lat=28.758 * u.deg,
    height=2396 * u.m
)

GBO_LOCATION = EarthLocation(
    lon=-79.8398 * u.deg,
    lat=38.4331 * u.deg,
    height=823 * u.m
)

GTC = Observer(
    location=GTC_LOCATION,
    name="GTC",
    timezone="UTC"
)

GBO = Observer(
    location=GBO_LOCATION,
    name="GBO",
    timezone="UTC"
)

# ── OBSERVATORY REGISTRY ──────────────────────────────────────────────────────
# To add a new observatory, simply append an entry to the appropriate sub-dict
# ("optical" or "radio") with these six fields:
#   full_name : human-readable name shown in the UI
#   lon / lat : decimal degrees (negative = West / South)
#   height    : metres above sea level
#   timezone  : IANA tz string (e.g. "America/Santiago")
#   short     : abbreviation used in plot titles and table headers
# No other code changes are required.
OBSERVATORY_REGISTRY = {
    "optical": {
        "GTC": {
            "full_name": "Gran Telescopio Canarias",
            "lon": -17.889, "lat": 28.758, "height": 2396,
            "timezone": "Atlantic/Canary", "short": "GTC"
        },
        "VLT": {
            "full_name": "Very Large Telescope (ESO)",
            "lon": -70.4045, "lat": -24.6275, "height": 2635,
            "timezone": "America/Santiago", "short": "VLT"
        },
        "Keck": {
            "full_name": "Keck Observatory",
            "lon": -155.4747, "lat": 19.8263, "height": 4145,
            "timezone": "Pacific/Honolulu", "short": "Keck"
        },
        "GeminiN": {
            "full_name": "Gemini North",
            "lon": -155.4691, "lat": 19.8238, "height": 4213,
            "timezone": "Pacific/Honolulu", "short": "Gem-N"
        },
        "GeminiS": {
            "full_name": "Gemini South",
            "lon": -70.7236, "lat": -30.2407, "height": 2722,
            "timezone": "America/Santiago", "short": "Gem-S"
        },
        "WHT": {
            "full_name": "William Herschel Telescope",
            "lon": -17.878, "lat": 28.760, "height": 2344,
            "timezone": "Atlantic/Canary", "short": "WHT"
        },
        "NOT": {
            "full_name": "Nordic Optical Telescope",
            "lon": -17.885, "lat": 28.757, "height": 2382,
            "timezone": "Atlantic/Canary", "short": "NOT"
        },
    },
    "radio": {
        "GBO": {
            "full_name": "Green Bank Observatory (GBT)",
            "lon": -79.8398, "lat": 38.4331, "height": 823,
            "timezone": "US/Eastern", "short": "GBO"
        },
        "FAST": {
            "full_name": "Five-hundred-meter Aperture Spherical Telescope",
            "lon": 106.8567, "lat": 25.6537, "height": 1110,
            "timezone": "Asia/Shanghai", "short": "FAST"
        },
        "Parkes": {
            "full_name": "Parkes Observatory (Murriyang)",
            "lon": 148.2635, "lat": -32.9994, "height": 415,
            "timezone": "Australia/Sydney", "short": "PKS"
        },
        "CHIME": {
            "full_name": "Canadian Hydrogen Intensity Mapping Experiment",
            "lon": -119.6175, "lat": 49.3208, "height": 555,
            "timezone": "America/Vancouver", "short": "CHIME"
        },
        "WSRT": {
            "full_name": "Westerbork Synthesis Radio Telescope",
            "lon": 6.6033, "lat": 52.9148, "height": 16,
            "timezone": "Europe/Amsterdam", "short": "WSRT"
        },
        "MeerKAT": {
            "full_name": "MeerKAT Radio Telescope",
            "lon": 21.4432, "lat": -30.7130, "height": 1038,
            "timezone": "Africa/Johannesburg", "short": "MeerKAT"
        },
        "Effelsberg": {
            "full_name": "Effelsberg Radio Telescope",
            "lon": 6.8836, "lat": 50.5247, "height": 319,
            "timezone": "Europe/Berlin", "short": "Effelsberg"
        },
        "uGMRT": {
            "full_name": "Upgraded Giant Metrewave Radio Telescope",
            "lon": 74.0497, "lat": 19.0948, "height": 650,
            "timezone": "Asia/Kolkata", "short": "uGMRT"
        },
    }
}


def build_observer(obs_type, key):
    """Build an astroplan Observer and EarthLocation from OBSERVATORY_REGISTRY.
    
    Returns (Observer, EarthLocation) so callers can use either object as needed.
    obs_type must be "optical" or "radio"; key is a registry dict key.
    """
    info = OBSERVATORY_REGISTRY[obs_type][key]
    location = EarthLocation(
        lon=info["lon"] * u.deg,
        lat=info["lat"] * u.deg,
        height=info["height"] * u.m
    )
    observer = Observer(location=location, name=info["short"], timezone="UTC")
    return observer, location


def highlight_windows(ax, windows):
    if windows:
        for w in windows:
            try:
                t_start = Time(w['start'])
                t_end = Time(w['end'])
                ax.axvspan(t_start.plot_date, t_end.plot_date, color='#2ecc71', alpha=0.3)
            except:
                pass

def shade_twilight_manual(ax, observer, time_grid):
    """Manually adds twilight shading to GBO altitude plot."""
    sun_coords = get_sun(time_grid).transform_to(AltAz(obstime=time_grid, location=observer.location))
    sun_alt = sun_coords.alt.deg
    for i in range(len(time_grid) - 1):
        t_start, t_end = time_grid[i].plot_date, time_grid[i+1].plot_date
        alt = sun_alt[i]
        if alt <= -18: # Astronomical Night
            ax.axvspan(t_start, t_end, color='#a9a9a9', alpha=0.2, zorder=0)
        elif alt <= -12: # Astronomical Twilight
            ax.axvspan(t_start, t_end, color='#bdbdbd', alpha=0.2, zorder=0)
        elif alt <= -6: # Nautical Twilight
            ax.axvspan(t_start, t_end, color='#d3d3d3', alpha=0.2, zorder=0)
        elif alt <= 0: # Civil Twilight
            ax.axvspan(t_start, t_end, color='#e9e9e9', alpha=0.2, zorder=0)

def generate_airmass_plot(coord, night_date_str, mode="UTC", observer_name="GTC", windows=None,
                           observer_obj=None, obs_type="optical", plot_tz=None, plot_tz_label=None):
    """
    Generate a visibility plot for a given observatory.

    New optional parameters (all backward-compatible, default to legacy behaviour):
      observer_obj  : astroplan Observer built from OBSERVATORY_REGISTRY; overrides observer_name.
      obs_type      : "optical" → airmass-vs-time plot; "radio" → altitude-vs-time plot.
      plot_tz       : ZoneInfo for the x-axis tick labels; overrides the mode-string lookup.
      plot_tz_label : Human-readable timezone label for the x-axis title.

    BUG FIX — time labels: DateFormatter now receives the tz argument so that local-time
    display modes actually show the correct hours instead of UTC digits.
    """
    try:
        # Use explicitly provided observer, or fall back to legacy name-based selection
        observer = observer_obj if observer_obj is not None else (GTC if observer_name == "GTC" else GBO)
        
        time_center = Time(f"{night_date_str} 00:00:00") + 1 * u.day 
        time_grid = time_center + np.linspace(-12, 12, 150) * u.hour
        
        fig, ax = plt.subplots(figsize=(6, 4))
        target = FixedTarget(coord=coord, name="Target")

        # 1. ESTABLISH TIMEZONE AND LABEL
        # plot_tz / plot_tz_label (dynamic observatory path) take precedence.
        # Otherwise fall back to the legacy mode-string mapping.
        if plot_tz is not None and plot_tz_label is not None:
            tz = plot_tz
            time_label = plot_tz_label
        elif mode == "GTC_LOCAL" or mode == "LOCAL":
            tz = ZoneInfo("Atlantic/Canary")
            time_label = "GTC Local"
        elif mode == "GBO_LOCAL":
            tz = ZoneInfo("US/Eastern")
            time_label = "GBO Local"
        else:
            tz = ZoneInfo("UTC")
            time_label = "UTC"

        # 2. CHOOSE PLOT STYLE
        # obs_type drives the decision; legacy fallback checks observer_name == "GBO"
        use_radio_style = (obs_type == "radio") or (observer_obj is None and observer_name == "GBO")

        if use_radio_style:
            shade_twilight_manual(ax, observer, time_grid)
            altaz = target.coord.transform_to(AltAz(obstime=time_grid, location=observer.location))
            ax.plot(time_grid.plot_date, altaz.alt.deg, color='C0', label='Target', linewidth=1.5, zorder=5)
            
            try:
                moon = get_body("moon", time_grid, location=observer.location)
                moon_altaz = moon.transform_to(AltAz(obstime=time_grid, location=observer.location))
                ax.plot(time_grid.plot_date, moon_altaz.alt.deg, color='gray', linestyle='--', label='Moon', alpha=0.6, zorder=4)
            except: pass
            
            ax.set_ylabel("Altitude [degrees]")
            ax.set_ylim(0, 90)
            ax.set_xlim(time_grid[0].plot_date, time_grid[-1].plot_date)
        else:
            plot_airmass(target, observer, time_center, ax=ax, brightness_shading=True)
            try:
                # Use observer.location so this works for any optical observatory, not just GTC
                moon_obs = get_body("moon", time_grid, location=observer.location)
                moon_altaz_obs = moon_obs.transform_to(AltAz(obstime=time_grid, location=observer.location))
                moon_airmass = moon_altaz_obs.secz
                moon_airmass = np.ma.masked_where((moon_airmass < 1) | (moon_airmass > 3.0), moon_airmass)
                ax.plot(time_grid.plot_date, moon_airmass, color='gray', linestyle='--', label='Moon', alpha=0.6, zorder=10)
            except: pass
            ax.set_ylabel("Airmass")
            ax.set_ylim(3.0, 1.0)

        highlight_windows(ax, windows)
            
        # ax.xaxis.set_major_formatter(DateFormatter('%H:%M', tz=tz))
        # BUG FIX: pass tz so that local-time modes display the correct local hour digits
        ax.xaxis.set_major_formatter(DateFormatter('%H:%M', tz=tz))

        ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(byhour=[12, 15, 18, 21, 0, 3, 6, 9, 12]))
        
        plt.setp(ax.get_xticklabels(), rotation=0, ha='center')

        # FIXED: Ensure the label uses the dynamic time_label for BOTH observers
        ax.set_xlabel(f"Time ({time_label})")
        ax.set_title(f"{observer.name} Visibility")
        
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(
            by_label.values(), 
            by_label.keys(), 
            loc='upper right', 
            fontsize='small',      
            handletextpad=0.8,     
            borderpad=0.5          
        )
        ax.grid(True, alpha=0.2)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=72)
        buf.seek(0)
        plt.close(fig)
        return base64.b64encode(buf.read()).decode('utf-8')
    except Exception as e:
        print(f"Plot Error: {e}", flush=True)
        return None
    

# OLD generate_airmass_plot
# def generate_airmass_plot(coord, night_date_str, mode="UTC", observer_name="GTC", windows=None):
#     try:
#         observer = GTC if observer_name == "GTC" else GBO
#         time_midnight = Time(f"{night_date_str} 00:00:00") + 1 * u.day 
#         target = FixedTarget(coord=coord, name="Target")

#         fig, ax = plt.subplots(figsize=(6, 4)) 
#         plot_airmass(target, observer, time_midnight, ax=ax, brightness_shading=True)
        
#         # --- MOON PLOT ---
#         try:
#             # Generate time grid matching the plot (approx noon to noon)
#             time_grid = time_midnight + np.linspace(-12, 12, 100) * u.hour
#             moon = get_body("moon", time_grid, location=observer.location)
#             moon_altaz = moon.transform_to(AltAz(obstime=time_grid, location=observer.location))
#             moon_airmass = moon_altaz.secz
#             # Mask below horizon
#             moon_airmass = np.ma.masked_where(moon_airmass < 1, moon_airmass)
#             ax.plot(time_grid.plot_date, moon_airmass, color='gray', linestyle='--', label='Moon', alpha=0.6)
#         except Exception as e:
#             print(f"Moon Plot Error: {e}", flush=True)
#         # -----------------------
        
#         # We keep this to ensure the Target label is shown, even without the Moon
#         ax.legend(loc='best') 

#         highlight_windows(ax, windows)

#         time_label = "UTC"
#         if mode == "LOCAL":
#             tz = ZoneInfo("Atlantic/Canary")
#             ax.xaxis.set_major_formatter(DateFormatter('%H:%M', tz=tz))
#             time_label = "GTC Local"
#         else:
#             tz = ZoneInfo("UTC")
#             ax.xaxis.set_major_formatter(DateFormatter('%H:%M', tz=tz))

#         ax.set_xlabel(f"Time from {night_date_str} [{time_label}]")
#         ax.set_title(f"{observer_name} Airmass ({time_label})")
#         ax.grid(True, alpha=0.3)
#         plt.tight_layout()

#         buf = io.BytesIO()
#         plt.savefig(buf, format='png')
#         buf.seek(0)
#         img_str = base64.b64encode(buf.read()).decode('utf-8')
#         plt.close(fig) 
#         return img_str
#     except Exception as e:
#         print(f"Plot Error ({observer_name} - {mode}, flush=True): {e}")
#         return None

# joint plot
def generate_joint_plot(coord, night_date_str, mode="UTC", windows=None,
                         optical_observer=None, radio_observer=None):
    try:
        # Use provided observers or fall back to legacy GTC/GBO
        opt_obs = optical_observer if optical_observer is not None else GTC
        rad_obs = radio_observer if radio_observer is not None else GBO

        time_midnight = Time(f"{night_date_str} 00:00:00") + 1 * u.day 
        target = FixedTarget(coord=coord, name=" Target")

        fig, ax = plt.subplots(figsize=(6, 4))
        
        plot_airmass(target, opt_obs, time_midnight, ax=ax, brightness_shading=True, 
                     style_kwargs={'color': 'blue', 'linewidth': 1.5})
        
        plot_airmass(target, rad_obs, time_midnight, ax=ax, brightness_shading=False, 
                     style_kwargs={'color': 'red', 'linewidth': 1.5, 'linestyle': '--'})
        
        # --- MOON PLOT COMMENTED OUT ---
        try:
            time_grid = time_midnight + np.linspace(-12, 12, 100) * u.hour
            moon = get_body("moon", time_grid, location=opt_obs.location)
            moon_altaz = moon.transform_to(AltAz(obstime=time_grid, location=opt_obs.location))
            moon_airmass = moon_altaz.secz
            moon_airmass = np.ma.masked_where(moon_airmass < 1, moon_airmass)
            ax.plot(time_grid.plot_date, moon_airmass, color='gray', linestyle=':', label='Moon', alpha=0.6)
        except Exception:
            pass
        # ------------------------------------------------------------------

        highlight_windows(ax, windows)

        legend_elements = [
            Line2D([0], [0], color='blue', lw=1.5, label=f'{opt_obs.name} (Optical)'),
            Line2D([0], [0], color='red', lw=1.5, linestyle='--', label=f'{rad_obs.name} (Radio)'),
            
            Line2D([0], [0], color='gray', linestyle=':', label='Moon'), # Commented out from legend


            matplotlib.patches.Patch(facecolor='#2ecc71', alpha=0.3, label='Joint Window')
        ]
        ax.legend(handles=legend_elements, loc='upper right', fontsize='small')

        time_label = "UTC"
        if mode == "LOCAL":
            tz = ZoneInfo("Atlantic/Canary")
            # ax.xaxis.set_major_formatter(DateFormatter('%H:%M', tz=tz))
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))

            time_label = "GTC Local"
        else:
            tz = ZoneInfo("UTC")
            # ax.xaxis.set_major_formatter(DateFormatter('%H:%M', tz=tz))
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))

        ax.set_xlabel(f"Time from {night_date_str} [{time_label}]")
        ax.set_title(f"Joint Visibility Intersection")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig) 
        return img_str
    except Exception as e:
        print(f"Joint Plot Error ({mode}, flush=True): {e}", flush=True)
        return None

def get_local_time_str(iso_time_str, tz_name="Atlantic/Canary"):
    try:
        dt_utc = datetime.fromisoformat(iso_time_str).replace(tzinfo=ZoneInfo("UTC"))
        dt_local = dt_utc.astimezone(ZoneInfo(tz_name))
        return dt_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return iso_time_str

def get_darkness_window(date, optical_observer=None, optical_tz_name="Atlantic/Canary"):
    """Return astronomical darkness start/end for the given date at the optical observatory.
    
    New optional params:
      optical_observer : astroplan Observer; defaults to legacy GTC if not provided.
      optical_tz_name  : IANA timezone string used to compute local-time strings.
    """
    obs = optical_observer if optical_observer is not None else GTC
    time_noon = Time(f"{date} 12:00:00")
    try:
        t_start = obs.twilight_evening_astronomical(time_noon, which='next')
        t_end = obs.twilight_morning_astronomical(time_noon, which='next')
        return {
            "start_utc": t_start.iso,
            "end_utc": t_end.iso,
            "start_local": get_local_time_str(t_start.iso, tz_name=optical_tz_name),
            "end_local": get_local_time_str(t_end.iso, tz_name=optical_tz_name)
        }
    except Exception:
        return None

def is_astronomical_dark(t, optical_location=None):
    """Check whether the sun is below -18° at the optical observatory at time t."""
    loc = optical_location if optical_location is not None else GTC_LOCATION
    sun_altaz = get_sun(t).transform_to(AltAz(obstime=t, location=loc))
    return sun_altaz.alt < -18 * u.deg

# moon condition
def determine_moon_condition(t, coord, airmass_limit, start_date, end_date, optical_location=None):
    #observing conditions based on moon position/illumination.
    loc = optical_location if optical_location is not None else GTC_LOCATION
    try:
        moon = get_body("moon", t, location=loc)
        moon_altaz = moon.transform_to(AltAz(obstime=t, location=loc))
        moon_alt = moon_altaz.alt.deg
        
        illumination = moon_illumination(t) # 0.0 to 1.0
        separation = moon.separation(coord).deg

        #target airmass at this specific time
        target_altaz = coord.transform_to(AltAz(obstime=t, location=loc))
        target_airmass = target_altaz.secz

        print(f"Log Time (UTC, flush=True)       : {t.iso}", flush=True)
        print(f"Request Range        : {start_date} to {end_date}", flush=True)
        print(f"Target RA/Dec        : {coord.ra.to_string(unit=u.hour, sep=':', precision=2, flush=True)} , {coord.dec.to_string(unit=u.deg, sep=':', precision=2)}", flush=True)

        print(f"Current Airmass      : {target_airmass:.2f} (Limit: {airmass_limit}, flush=True)", flush=True)
        print(f"Moon Illumination    : {illumination * 100:.2f}%", flush=True)
        print(f"Moon Altitude        : {moon_alt:.2f}°", flush=True)
        print(f"Moon Separation      : {separation:.2f}°", flush=True)

        #1 dark Conditions
        #moon below horizon OR (Sep >= 90 AND Illum <= 25%)
        if moon_alt < 0:
            print("dark", flush=True)
            return "Dark"
        if separation >= 90 and illumination <= 0.25:
            print("dark", flush=True)
            return "Dark"

        #2 bright Conditions
        if illumination >= 0.70 and moon_alt > 10:
            print("bright", flush=True)
            return "Bright"
        
        if separation <= 45:
            print("bright", flush=True)
            return "Bright"

        print("gray", flush=True)
        return "Gray"

    except Exception as e:
        return "Unknown"

def is_visible_at_time(coord, t, airmass_limit, optical_location=None, radio_location=None):
    #basic visibility checks (Horizon/Airmass)
    #relying on determine_moon_condition for the quality label only,
    #but we still strictly enforce astronomical dark time for optical.
    opt_loc = optical_location if optical_location is not None else GTC_LOCATION
    rad_loc = radio_location if radio_location is not None else GBO_LOCATION

    if not is_astronomical_dark(t, optical_location=opt_loc):
        return False

    altaz_gtc = coord.transform_to(AltAz(obstime=t, location=opt_loc))
    visible_gtc = (altaz_gtc.alt > 0 * u.deg) and (altaz_gtc.secz <= airmass_limit)

    altaz_gbo = coord.transform_to(AltAz(obstime=t, location=rad_loc))
    visible_gbo = altaz_gbo.alt >= 5 * u.deg

    return visible_gtc and visible_gbo

def compute_nightly_windows(coord, date_str, airmass_limit, start_date, end_date, step_min=10,
                              optical_observer=None, optical_location=None, radio_location=None,
                              optical_tz_name="Atlantic/Canary", radio_tz_name="US/Eastern"):
    """Compute joint visibility windows for one night.

    New optional params (all default to legacy GTC/GBO behaviour):
      optical_observer : astroplan Observer for the optical site (darkness computation).
      optical_location : EarthLocation for the optical site (airmass + sun + moon checks).
      radio_location   : EarthLocation for the radio site (elevation check).
      optical_tz_name  : IANA tz string to format start_local / end_local strings.
      radio_tz_name    : IANA tz string to format start_radio_local / end_radio_local strings.
    """
    darkness = get_darkness_window(date_str, optical_observer=optical_observer,
                                   optical_tz_name=optical_tz_name)
    if not darkness: return []

    time_start = Time(darkness["start_utc"])
    time_end   = Time(darkness["end_utc"])
    times = time_start + np.arange(0, (time_end - time_start).to(u.minute).value, step_min) * u.minute

    good_times = [
        t for t in times
        if is_visible_at_time(coord, t, airmass_limit,
                               optical_location=optical_location,
                               radio_location=radio_location)
    ]
    if not good_times:
        # Log the reason there is no window using the midpoint of the dark period
        try:
            midpoint = time_start + (time_end - time_start) * 0.5
            opt_loc = optical_location if optical_location is not None else GTC_LOCATION
            rad_loc = radio_location if radio_location is not None else GBO_LOCATION
            altaz_opt = coord.transform_to(AltAz(obstime=midpoint, location=opt_loc))
            altaz_rad = coord.transform_to(AltAz(obstime=midpoint, location=rad_loc))
            sun_altaz = get_sun(midpoint).transform_to(AltAz(obstime=midpoint, location=opt_loc))
            print(f"Log Time (UTC, flush=True)       : {midpoint.iso}")
            print(f"Date                 : {date_str}  [NO JOINT WINDOW]", flush=True)
            print(f"Target RA/Dec        : {coord.ra.to_string(unit=u.hour, sep=':', precision=2, flush=True)} , {coord.dec.to_string(unit=u.deg, sep=':', precision=2)}")
            print(f"Optical Airmass      : {altaz_opt.secz:.2f}  Alt: {altaz_opt.alt.deg:.2f}  (Limit: {airmass_limit}, flush=True)")
            print(f"Radio Altitude       : {altaz_rad.alt.deg:.2f}  (Min: 5, flush=True)")
            print(f"Sun Altitude         : {sun_altaz.alt.deg:.2f}  (Dark if < -18, flush=True)")
        except Exception as e:
            print(f"Date: {date_str}  [NO JOINT WINDOW]  (log error: {e}, flush=True)")
        return []

    windows = []
    start = good_times[0]
    prev = good_times[0]

    for t in good_times[1:]:
        if (t - prev).to(u.minute).value <= step_min + 1:
            prev = t
        else:
            windows.append((start, prev))
            start = t
            prev = t
    windows.append((start, prev))

    formatted_windows = []
    

    for s, e in windows:
        duration_hr = (e - s).to(u.hour).value
        if duration_hr < 2.0:
            midpoint = s + (e - s) * 0.5
            opt_loc = optical_location if optical_location is not None else GTC_LOCATION
            rad_loc = radio_location if radio_location is not None else GBO_LOCATION
            altaz_opt = coord.transform_to(AltAz(obstime=midpoint, location=opt_loc))
            altaz_rad = coord.transform_to(AltAz(obstime=midpoint, location=rad_loc))
            print(f"Log Time (UTC, flush=True)       : {midpoint.iso}")
            print(f"Date                 : {date_str}  [NO JOINT WINDOW — window {duration_hr:.2f}h < 2h minimum]", flush=True)
            print(f"Target RA/Dec        : {coord.ra.to_string(unit=u.hour, sep=':', precision=2, flush=True)} , {coord.dec.to_string(unit=u.deg, sep=':', precision=2)}")
            print(f"Optical Airmass      : {altaz_opt.secz:.2f}  Alt: {altaz_opt.alt.deg:.2f}  (Limit: {airmass_limit}, flush=True)")
            print(f"Radio Altitude       : {altaz_rad.alt.deg:.2f}  (Min: 5, flush=True)")
            continue

        midpoint = s + (e - s)* 0.5
        condition = determine_moon_condition(midpoint, coord, airmass_limit, start_date, end_date,
                                             optical_location=optical_location)
        
        formatted_windows.append({
            "start": s.iso,
            "end": e.iso,
            "start_local": get_local_time_str(s.iso, tz_name=optical_tz_name),
            "end_local": get_local_time_str(e.iso, tz_name=optical_tz_name),
            # Radio-local times so the frontend can display them without JS timezone math
            "start_radio_local": get_local_time_str(s.iso, tz_name=radio_tz_name),
            "end_radio_local": get_local_time_str(e.iso, tz_name=radio_tz_name),
            "duration_hours": round(duration_hr, 2),
            "condition": condition 
        })


    return formatted_windows

def process_date_range(coord, start_date_str, end_date_str, airmass_limit,
                        optical_key="GTC", radio_key="GBO"):
    """Process the full date range, generating windows and plots for each night.

    New params:
      optical_key : key into OBSERVATORY_REGISTRY["optical"]
      radio_key   : key into OBSERVATORY_REGISTRY["radio"]

    BUG FIX — low airmass / no windows: results are now always appended (with
    total_observable_hours=0.0 and an empty windows list) so that plots are
    available for every night regardless of whether a joint window was found.
    """
    results = []

    # Build observers once; pass them through to every sub-call
    optical_observer, optical_location = build_observer("optical", optical_key)
    radio_observer, radio_location     = build_observer("radio", radio_key)

    optical_tz_name = OBSERVATORY_REGISTRY["optical"][optical_key]["timezone"]
    radio_tz_name   = OBSERVATORY_REGISTRY["radio"][radio_key]["timezone"]
    optical_short   = OBSERVATORY_REGISTRY["optical"][optical_key]["short"]
    radio_short     = OBSERVATORY_REGISTRY["radio"][radio_key]["short"]

    optical_tz = ZoneInfo(optical_tz_name)
    radio_tz   = ZoneInfo(radio_tz_name)
    
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    delta_days = (end_date - start_date).days + 1
    

    # if delta_days > 31: 
    #     delta_days = 31 #cap at 1 month for now as it is crashing 

    import threading as _threading
    _tid = _threading.current_thread().name

    for i in range(delta_days):
        date_obj = start_date + timedelta(days=i)
        date_str = date_obj.strftime("%Y-%m-%d")
        print(f"[{_tid}] Night {i+1}/{delta_days}: {date_str} — computing…", flush=True)

        windows = compute_nightly_windows(
            coord, date_str, airmass_limit, start_date_str, end_date_str,
            optical_observer=optical_observer, optical_location=optical_location,
            radio_location=radio_location,
            optical_tz_name=optical_tz_name, radio_tz_name=radio_tz_name
        )
        
        darkness = get_darkness_window(date_str, optical_observer=optical_observer,
                                        optical_tz_name=optical_tz_name)

        # 1. UTC Plots
        plot_optical_utc = generate_airmass_plot(
            coord, date_str, mode="UTC", observer_name=optical_short, windows=windows,
            observer_obj=optical_observer, obs_type="optical",
            plot_tz=ZoneInfo("UTC"), plot_tz_label="UTC"
        )
        plot_radio_utc = generate_airmass_plot(
            coord, date_str, mode="UTC", observer_name=radio_short, windows=windows,
            observer_obj=radio_observer, obs_type="radio",
            plot_tz=ZoneInfo("UTC"), plot_tz_label="UTC"
        )
        
        # 2. Optical-local time axis plots (both observatories on the same time reference)
        plot_optical_optlocal = generate_airmass_plot(
            coord, date_str, mode="LOCAL", observer_name=optical_short, windows=windows,
            observer_obj=optical_observer, obs_type="optical",
            plot_tz=optical_tz, plot_tz_label=f"{optical_short} Local"
        )
        plot_radio_optlocal = generate_airmass_plot(
            coord, date_str, mode="LOCAL", observer_name=radio_short, windows=windows,
            observer_obj=radio_observer, obs_type="radio",
            plot_tz=optical_tz, plot_tz_label=f"{optical_short} Local"
        )
        
        # 3. Radio-local time axis plots (both observatories on the same time reference)
        plot_optical_radlocal = generate_airmass_plot(
            coord, date_str, mode="GBO_LOCAL", observer_name=optical_short, windows=windows,
            observer_obj=optical_observer, obs_type="optical",
            plot_tz=radio_tz, plot_tz_label=f"{radio_short} Local"
        )
        plot_radio_radlocal = generate_airmass_plot(
            coord, date_str, mode="GBO_LOCAL", observer_name=radio_short, windows=windows,
            observer_obj=radio_observer, obs_type="radio",
            plot_tz=radio_tz, plot_tz_label=f"{radio_short} Local"
        )

        # BUG FIX: always append so plots are accessible even when no joint window exists.
        # Previously the entire day was silently skipped when windows was empty.
        total_observable_hours = round(
            sum(w['duration_hours'] for w in windows), 2
        ) if windows else 0.0

        # Compute moon condition at dark-period midpoint for no-window nights so the
        # table can still show Dark / Gray / Bright instead of "—".
        night_moon_condition = None
        if not windows and darkness:
            try:
                t_mid = Time(darkness["start_utc"]) + (Time(darkness["end_utc"]) - Time(darkness["start_utc"])) * 0.5
                night_moon_condition = determine_moon_condition(
                    t_mid, coord, airmass_limit, start_date_str, end_date_str,
                    optical_location=optical_location
                )
            except Exception:
                night_moon_condition = "Unknown"

        results.append({
            "date": date_str, 
            "windows": windows,          # may be empty list — that is intentional
            "darkness": darkness,
            "total_observable_hours": total_observable_hours,
            "night_moon_condition": night_moon_condition,  # set only when no windows
            # New unified key names (replaces gtc/gbo-specific names)
            "plot_optical_utc":      plot_optical_utc,
            "plot_optical_optlocal": plot_optical_optlocal,
            "plot_radio_utc":        plot_radio_utc,
            "plot_radio_radlocal":   plot_radio_radlocal,
            "plot_optical_radlocal": plot_optical_radlocal,
            "plot_radio_optlocal":   plot_radio_optlocal,
        })

    return results

def run_pipeline(ra, dec, start_date=None, end_date=None, airmass_limit=2.5,
                  optical_key="GTC", radio_key="GBO"):
    #default to today if no start date
    if start_date is None: 
        start_date = Time.now().strftime("%Y-%m-%d")
    #default to 7 days if no end date
    if end_date is None:
        end_dt = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=6)
        end_date = end_dt.strftime("%Y-%m-%d")

    try: 
        coord = SkyCoord(ra, dec, unit=(u.hourangle, u.deg), frame="icrs")
    except Exception as e: 
        return {"error": f"Invalid coordinates: {e}"}

    # Validate observatory keys before doing any heavy computation
    if optical_key not in OBSERVATORY_REGISTRY["optical"]:
        return {"error": f"Unknown optical observatory: '{optical_key}'"}
    if radio_key not in OBSERVATORY_REGISTRY["radio"]:
        return {"error": f"Unknown radio observatory: '{radio_key}'"}

    optical_observer, optical_location = build_observer("optical", optical_key)
    radio_observer,   radio_location   = build_observer("radio",   radio_key)
    optical_tz_name = OBSERVATORY_REGISTRY["optical"][optical_key]["timezone"]
    radio_tz_name   = OBSERVATORY_REGISTRY["radio"][radio_key]["timezone"]

    # FIX: Pass start_date and end_date as required by compute_nightly_windows
    tonight_windows = compute_nightly_windows(
        coord, start_date, airmass_limit, start_date, end_date,
        optical_observer=optical_observer, optical_location=optical_location,
        radio_location=radio_location,
        optical_tz_name=optical_tz_name, radio_tz_name=radio_tz_name
    )
    tonight_darkness = get_darkness_window(start_date, optical_observer=optical_observer,
                                            optical_tz_name=optical_tz_name)
    
    #process the full requested range date
    date_range_results = process_date_range(
        coord, start_date, end_date, airmass_limit,
        optical_key=optical_key, radio_key=radio_key
    )

    nightly_totals = [
        day["total_observable_hours"]
        for day in date_range_results
        if "total_observable_hours" in day
    ]

    average_observable_hours = (
        round(sum(nightly_totals) / len(nightly_totals), 2)
        if nightly_totals else 0.0
    )

    return {
        "ra_input": ra, 
        "dec_input": dec, 
        "ra_deg": round(coord.ra.deg, 6), 
        "dec_deg": round(coord.dec.deg, 6),
        # Include selected observatory metadata so the frontend can show names/labels
        "optical_obs": OBSERVATORY_REGISTRY["optical"][optical_key],
        "radio_obs":   OBSERVATORY_REGISTRY["radio"][radio_key],
        "tonight": {
            "date": start_date, 
            "windows": tonight_windows, 
            "darkness": tonight_darkness
        },
        "next_7_days": date_range_results, #keeping key name for frontend compatibility, but it contains full range
        "average_observable_hours": average_observable_hours

    }



if __name__ == "__main__":
    # 1. Run the pipeline
    start_date_str = "2026-10-29"
    end_date_str = "2027-02-08"
    # ra_val, dec_val = "01:58:00.8", "+65:43:00.3"
    # ra_val, dec_val = "05:07:57.6", "+26:11:24.0"
    # ra_val, dec_val = "23:09:04.9", "+48:42:25.0"
    ra_val, dec_val = "21:27:39.9", "+04:19:45.7"
    ra_val, dec_val = "19:19:33", "+86:03:52.1"




    res = run_pipeline(ra_val, dec_val, start_date_str, end_date_str, 2.0)

    # 2. Prepare for Logging and CSV generation
    csv_filename = "observation_windows.csv"
    csv_header = ['Date', 'Start Time (UTC)', 'End Time (UTC)', 'Duration (hours)', 'Moon Condition', 'RA', 'Dec', 'Avg Observable Hours']
    log_data = []


    print(f"{'DATE':<12} | {'START (UTC, flush=True)':<20} | {'END (UTC)':<20} | {'DUR':<6} | {'MOON'}")

    for day in res['next_7_days']:
        date_label = day['date']
        
        for w in day['windows']:
            # Extract values for logging and CSV
            row = {
                'Date': date_label,
                'Start Time (UTC)': w['start'],
                'End Time (UTC)': w['end'],
                'Duration (hours)': w['duration_hours'],
                'Moon Condition': w['condition'],
                'RA': ra_val,
                'Dec': dec_val,
                'Avg Observable Hours': res['average_observable_hours']
            }

            log_data.append(row)

            # Print to terminal log
            print(f"{row['Date']:<12} | {row['Start Time (UTC, flush=True)']:<20} | {row['End Time (UTC)']:<20} | {row['Duration (hours)']:<6} | {row['Moon Condition']}")

        #3. Save the images 
        # plots_to_save = {
        #     # UTC Plots
        #     f"gtc_utc_{date_label}.png": day.get('plot_gtc_utc'),
        #     f"gbo_utc_{date_label}.png": day.get('plot_gbo_utc'),
            
        #     # GTC Local Time Plots
        #     f"gtc_local_at_gtc_{date_label}.png": day.get('plot_gtc_local'),
        #     f"gbo_local_at_gtc_{date_label}.png": day.get('plot_gbo_gtc_local'),
            
        #     # GBO Local Time Plots
        #     f"gtc_local_at_gbo_{date_label}.png": day.get('plot_gtc_gbo_local'),
        #     f"gbo_local_at_gbo_{date_label}.png": day.get('plot_gbo_local')
        # }

        # for filename, img_data in plots_to_save.items():
        #     if img_data:
        #         with open(filename, "wb") as f:
        #             f.write(base64.b64decode(img_data))

    # 4. Write to CSV file
    with open(csv_filename, mode='w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=csv_header)
        writer.writeheader()
        writer.writerows(log_data)
        # footer
        writer.writerow({
        'Date': 'Average',
        'Avg Observable Hours': res['average_observable_hours']
        })