"""Database of data brokers and their opt-out procedures.

Each entry: name, opt_out_url, type ("form" or "email"), required_fields,
instructions, expected_days_to_removal. URLs point at each broker's public
opt-out / suppression page.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Broker:
    key: str
    name: str
    opt_out_url: str
    type: str  # "form" | "email"
    required_fields: tuple[str, ...] = ("name",)
    instructions: str = ""
    expected_days_to_removal: int = 14
    contact_email: str = ""
    search_url: str = ""  # template with {query} for exposure checks


def _b(key, name, url, kind="form", fields=("name",), notes="", days=14, email="", search=""):
    return Broker(
        key=key,
        name=name,
        opt_out_url=url,
        type=kind,
        required_fields=tuple(fields),
        instructions=notes,
        expected_days_to_removal=days,
        contact_email=email,
        search_url=search,
    )


BROKERS: tuple[Broker, ...] = (
    _b("spokeo", "Spokeo", "https://www.spokeo.com/optout",
       fields=("profile_url", "email"),
       notes="Search yourself, copy the profile URL, submit it with your email, confirm via the link they send.",
       days=3),
    _b("whitepages", "Whitepages", "https://www.whitepages.com/suppression-requests",
       fields=("profile_url", "phone"),
       notes="Requires an automated phone verification call.", days=7),
    _b("beenverified", "BeenVerified", "https://www.beenverified.com/app/optout/search",
       fields=("name", "state", "email"),
       notes="Find your listing, click 'That's the one', confirm via email.", days=7),
    _b("intelius", "Intelius", "https://suppression.peopleconnect.us/login",
       fields=("email",),
       notes="PeopleConnect suppression portal also covers Instant Checkmate, TruthFinder and US Search.",
       days=7),
    _b("instantcheckmate", "Instant Checkmate", "https://suppression.peopleconnect.us/login",
       fields=("email",), notes="Handled by the PeopleConnect suppression portal.", days=7),
    _b("truthfinder", "TruthFinder", "https://suppression.peopleconnect.us/login",
       fields=("email",), notes="Handled by the PeopleConnect suppression portal.", days=7),
    _b("ussearch", "US Search", "https://suppression.peopleconnect.us/login",
       fields=("email",), notes="Handled by the PeopleConnect suppression portal.", days=7),
    _b("mylife", "MyLife", "https://www.mylife.com/ccpa/index.pubview",
       kind="email", fields=("name", "age", "address"),
       email="removalrequests@mylife.com",
       notes="Email your full name, age, current address and the profile URL; CCPA form also available.",
       days=10),
    _b("radaris", "Radaris", "https://radaris.com/control/privacy",
       fields=("profile_url", "email"), notes="Requires account creation or a signed request.", days=7),
    _b("pipl", "Pipl", "https://pipl.com/personal-information-removal-request",
       kind="email", fields=("name", "email"), email="support@pipl.com",
       notes="Submit the removal request form or email support with your details.", days=30),
    _b("truepeoplesearch", "TruePeopleSearch", "https://www.truepeoplesearch.com/removal",
       fields=("profile_url",), notes="Find your record, click 'Remove This Record'.", days=3),
    _b("fastpeoplesearch", "FastPeopleSearch", "https://www.fastpeoplesearch.com/removal",
       fields=("profile_url",), notes="Locate your record and follow the removal wizard.", days=3),
    _b("lexisnexis", "LexisNexis", "https://optout.lexisnexis.com/",
       fields=("name", "address", "reason"),
       notes="Requires identity verification; may request documentation by mail.", days=30),
    _b("acxiom", "Acxiom", "https://isapps.acxiom.com/optout/optout.aspx",
       fields=("name", "address", "email", "phone"),
       notes="Opt out of marketing data; confirm via the email they send.", days=14),
    _b("peekyou", "PeekYou", "https://www.peekyou.com/about/contact/optout/",
       fields=("profile_url", "name", "email"), days=10),
    _b("yasni", "Yasni", "https://www.yasni.com/",
       kind="email", fields=("name", "url"), email="support@yasni.com",
       notes="Yasni aggregates other sites; request removal at the original source, then email support.",
       days=30),
    _b("peoplefinder", "PeopleFinder", "https://www.peoplefinder.com/optout.php",
       fields=("name", "email", "state"), days=7),
    _b("peoplesmart", "PeopleSmart", "https://www.peoplesmart.com/app/optout/search",
       fields=("name", "state", "email"), days=7),
    _b("usapeoplesearch", "USA People Search", "https://www.usa-people-search.com/manage/",
       fields=("name", "state"), days=7),
    _b("411", "411.com", "https://www.whitepages.com/suppression-requests",
       fields=("profile_url", "phone"),
       notes="411.com listings are served by Whitepages; use its suppression tool.", days=7),
    _b("anywho", "AnyWho", "https://www.anywho.com/help/privacy",
       notes="Listings come from Whitepages data; suppressing there removes AnyWho results.", days=14),
    _b("classmates", "Classmates", "https://www.classmates.com/siteui/contact/remove-info",
       fields=("name", "email", "school"), days=14),
    _b("usphonebook", "USPhoneBook", "https://www.usphonebook.com/opt-out",
       fields=("profile_url", "email"), days=3),
    _b("thatsthem", "ThatsThem", "https://thatsthem.com/optout",
       fields=("name", "email", "address"), days=7),
    _b("numlookup", "NumLookup", "https://www.numlookup.com/opt-out",
       fields=("phone",), days=7),
    _b("addresses", "Addresses.com", "https://www.addresses.com/optout.php",
       fields=("name", "email", "state"), days=7),
    _b("callersmart", "CallerSmart", "https://www.callersmart.com/opt-out",
       fields=("phone",), days=7),
    _b("syncme", "Sync.me", "https://sync.me/optout/",
       fields=("phone",), days=7),
    _b("truecaller", "Truecaller", "https://www.truecaller.com/unlisting",
       fields=("phone",), notes="Unlisting removes your number from search results.", days=1),
    _b("wink", "Wink People Search", "https://wink.com/",
       kind="email", fields=("name", "url"), email="support@wink.com", days=30),
    _b("addressbook", "AddressBook / AddressSearch", "https://addresssearch.com/remove-info.php",
       fields=("name", "email"), days=7),
    _b("peoplelookup", "PeopleLookup", "https://www.peoplelookup.com/optout/",
       fields=("name", "state"), days=7),
    _b("publicrecordsnow", "PublicRecordsNow", "https://www.publicrecordsnow.com/static/view/optout/",
       fields=("name", "email", "state"), days=7),
    _b("411locate", "411 Locate", "https://www.411locate.com/",
       kind="email", fields=("name", "url"), email="support@411locate.com", days=14),
    _b("advancedbackgroundchecks", "AdvancedBackgroundChecks",
       "https://www.advancedbackgroundchecks.com/removal",
       fields=("profile_url", "email"), days=3),
    _b("ancestry", "Ancestry", "https://support.ancestry.com/s/contactsupport",
       kind="email", fields=("name", "record_url"), email="support@ancestry.com",
       notes="Request removal of living-person records via support.", days=30),
    _b("archives", "Archives.com", "https://www.archives.com/optout",
       fields=("name", "email"), days=14),
    _b("canada411", "Canada411", "https://www.canada411.ca/",
       kind="email", fields=("name", "phone"), email="c411@yp.ca", days=30),
    _b("centeda", "Centeda", "https://centeda.com/ng/control/privacy",
       fields=("profile_url", "email"), days=7),
    _b("cocofinder", "CocoFinder", "https://cocofinder.com/remove-my-info",
       fields=("profile_url", "email"), days=7),
    _b("cubib", "Cubib", "https://cubib.com/optout.php",
       fields=("name", "email"), days=7),
    _b("dataveria", "DataVeria", "https://dataveria.com/ng/control/privacy",
       fields=("profile_url", "email"), days=7),
    _b("clustrmaps", "ClustrMaps", "https://clustrmaps.com/bl/opt-out",
       fields=("profile_url", "email"), days=7),
    _b("golookup", "GoLookUp", "https://golookup.com/support/optout",
       fields=("name", "email"), days=14),
    _b("idtrue", "IDTrue", "https://www.idtrue.com/optout/",
       fields=("name", "email", "state"), days=7),
    _b("lookupanyone", "LookupAnyone", "https://www.lookupanyone.com/",
       kind="email", fields=("name", "url"), email="support@lookupanyone.com", days=14),
    _b("manta", "Manta", "https://www.manta.com/resources/contact-us/",
       kind="email", fields=("business_name", "url"), email="support@manta.com",
       notes="Business directory; request delisting via support.", days=30),
    _b("neighborreport", "Neighbor.Report", "https://neighbor.report/remove",
       fields=("address", "email"), days=7),
    _b("nuwber", "Nuwber", "https://nuwber.com/removal/link",
       fields=("profile_url",), days=3),
    _b("officialusa", "OfficialUSA", "https://www.officialusa.com/optout",
       kind="email", fields=("name", "url"), email="support@officialusa.com", days=14),
    _b("phoneowner", "PhoneOwner", "https://phoneowner.com/page/privacy",
       fields=("phone",), days=7),
    _b("rehold", "Rehold", "https://rehold.com/",
       kind="email", fields=("address", "url"), email="support@rehold.com", days=14),
    _b("searchbug", "SearchBug", "https://www.searchbug.com/peoplefinder/how-to-remove.aspx",
       kind="email", fields=("name", "url"), email="ccpa@searchbug.com", days=14),
    _b("smartbackgroundchecks", "SmartBackgroundChecks",
       "https://www.smartbackgroundchecks.com/optout",
       fields=("profile_url", "email"), days=3),
    _b("spyfly", "SpyFly", "https://www.spyfly.com/help-center/remove-info",
       fields=("name", "email"), days=14),
    _b("tellows", "Tellows", "https://www.tellows.com/",
       kind="email", fields=("phone",), email="support@tellows.com",
       notes="Phone-number reputation site; request deletion of your number page.", days=14),
    _b("usatrace", "USATrace", "http://www.usatrace.com/optout/",
       kind="email", fields=("name", "url"), email="privacy@usatrace.com", days=14),
    _b("veripages", "Veripages", "https://veripages.com/page/contact",
       fields=("profile_url", "email"), days=7),
    _b("xlek", "Xlek", "https://www.xlek.com/optout.php",
       fields=("name", "email"), days=7),
    _b("zoominfo", "ZoomInfo", "https://www.zoominfo.com/update/remove",
       fields=("email",), notes="Verify with your business email to manage/remove your profile.", days=14),
    _b("peoplebyname", "PeopleByName", "https://www.peoplebyname.com/remove.php",
       fields=("phone", "email"), days=7),
    _b("peoplesearchnow", "PeopleSearchNow", "https://www.peoplesearchnow.com/opt-out",
       fields=("name", "state"), days=7),
    _b("familytreenow", "FamilyTreeNow", "https://www.familytreenow.com/optout",
       fields=("profile_url",), days=3),
    _b("mugshotlook", "MugshotLook", "https://www.mugshotlook.com/optout",
       fields=("name", "email"), days=14),
    _b("unmask", "Unmask", "https://unmask.com/optout/",
       fields=("name", "email"), days=7),
    _b("privateeye", "PrivateEye", "https://www.privateeye.com/static/view/optout/",
       fields=("name", "email"), days=7),
    _b("verecor", "Verecor", "https://verecor.com/ng/control/privacy",
       fields=("profile_url", "email"), days=7),
    _b("findpeoplesearch", "FindPeopleSearch", "https://findpeoplesearch.com/customerservice/",
       fields=("name", "email"), days=14),
    _b("govarrestrecords", "GovernmentRegistry / Arrest Records",
       "https://www.governmentregistry.org/", kind="email",
       fields=("name", "url"), email="support@governmentregistry.org", days=30),
)


def all_brokers() -> list[Broker]:
    return list(BROKERS)


def get_broker(key: str) -> Broker | None:
    key = key.strip().lower()
    for broker in BROKERS:
        if broker.key == key or broker.name.lower() == key:
            return broker
    return None


def find_brokers(term: str) -> list[Broker]:
    term = term.strip().lower()
    return [b for b in BROKERS if term in b.key or term in b.name.lower()]
