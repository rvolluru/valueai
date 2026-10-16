"""Pure photo identity and narrow, serialized listing-result merges."""
import copy
import json
from urllib.parse import urlparse


class StalePipelineResult(RuntimeError):
    pass


def photo_key(url):
    if not isinstance(url, str):
        return ""
    path = urlparse(url).path
    return path if path.startswith('/v1/images/') else url


def original_urls(listing):
    generated = {photo_key(asset.get('image_url')) for asset in (listing.get('analysis') or {}).get('generated_assets', [])
                 if isinstance(asset, dict) and asset.get('synthetic')}
    entries = listing.get('listed_images') or listing.get('images') or [listing.get('image')]
    urls = [entry.get('p_img') or entry.get('d_img') if isinstance(entry, dict) else entry for entry in entries]
    return [url for url in urls if url and photo_key(url) not in generated]


def photo_signature(listing):
    return sorted(photo_key(url) for url in original_urls(listing))


def result_is_current(db, current, snapshot):
    latest = db.get_latest_listing_analysis_job(current['listing_id'], current['owner_subject'])
    return (latest and latest['job_id'] == snapshot['job_id']
            and photo_signature(current) == snapshot['photo_signature'])


def merge_result(db, snapshot, component, result):
    def transform(current):
        if not result_is_current(db, current, snapshot):
            return None
        analysis = copy.deepcopy(current.get('analysis') or {})
        fields = {}
        if component == 'pricing':
            baseline = snapshot['listing']
            if any(current.get(key) != baseline.get(key) for key in ('condition', 'size', 'category')):
                return None
            incoming = copy.deepcopy(result['analysis'])
            for key in ('generated_assets', 'presentation_assets'):
                if key in analysis:
                    incoming[key] = analysis[key]
            old_debug = analysis.get('debug') or {}
            incoming.setdefault('debug', {})['pipeline_results'] = old_debug.get('pipeline_results', {})
            analysis = incoming
            for key in ('title', 'brand', 'category', 'condition', 'size', 'description'):
                if key in result and current.get(key) == baseline.get(key):
                    fields[key] = result[key]
            fields['estimated_value'] = result['estimated_value']
            fields['source_item_id'] = result['source_item_id']
            if 'tags' in result and current.get('tags') == baseline.get('tags'):
                fields['tags_json'] = json.dumps(result['tags'])
            fields['status'] = 'Active' if str(current.get('status')).lower() == 'active' else result.get('status', 'Review')
        elif component == 'mannequin':
            asset = {**result, 'pipeline_job_id': snapshot['job_id']}
            assets = list(analysis.get('generated_assets') or [])
            if not any(entry.get('image_id') == asset['image_id'] for entry in assets):
                assets.append(asset)
            analysis['generated_assets'] = assets
            if str(current.get('status')).lower() != 'active':
                gallery = copy.deepcopy(current.get('listed_images') or current.get('images') or [])
                existing = {photo_key(entry.get('d_img') if isinstance(entry, dict) else entry) for entry in gallery}
                if photo_key(asset['image_url']) not in existing:
                    gallery.append({'p_img': asset['image_url'], 'd_img': asset['image_url'], 'is_hero': False})
                fields['images_json'] = json.dumps(gallery)
        elif component == 'staging':
            assets = [{**asset, 'pipeline_job_id': snapshot['job_id']} for asset in result]
            replacements = {photo_key(asset['source_image_url']): asset['image_url'] for asset in assets}
            gallery = copy.deepcopy(current.get('listed_images') or current.get('images') or [])
            for index, entry in enumerate(gallery):
                source = entry.get('p_img') or entry.get('d_img') if isinstance(entry, dict) else entry
                target = replacements.get(photo_key(source))
                if target:
                    gallery[index] = {**(entry if isinstance(entry, dict) else {}), 'p_img': source, 'd_img': target,
                                      'is_hero': entry.get('is_hero', index == 0) if isinstance(entry, dict) else index == 0}
                    if photo_key(current.get('image')) in {photo_key(source), photo_key(entry.get('d_img')) if isinstance(entry, dict) else photo_key(source)}:
                        fields['image'] = target
            fields['images_json'] = json.dumps(gallery)
            analysis['presentation_assets'] = assets
        else:
            raise ValueError('Unknown pipeline component')
        debug = analysis.get('debug') or {}
        debug['pipeline_results'] = {**debug.get('pipeline_results', {}), component: {'job_id': snapshot['job_id'], 'status': 'succeeded'}}
        analysis['debug'] = debug
        fields['analysis_json'] = json.dumps(analysis)
        return fields
    if not db.mutate_pipeline_listing(snapshot['listing_id'], snapshot['owner_subject'], transform):
        raise StalePipelineResult('Listing inputs changed or a newer analysis job superseded this result')


def mark_pricing_failure(db, snapshot):
    def transform(current):
        if result_is_current(db, current, snapshot) and str(current.get('status')).lower() == 'analyzing':
            return {'status': 'AnalysisFailed', 'tags_json': json.dumps(['Analysis failed'])}
        return None
    db.mutate_pipeline_listing(snapshot['listing_id'], snapshot['owner_subject'], transform)
