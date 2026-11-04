"""Summarize optional NSImage draw traces; this is usage evidence, not fidelity approval."""
import hashlib
import json
import math
from pathlib import Path


def undersampled(row):
    # Cropping and custom view transforms still need inspection before
    # declaring a resolution defect from these whole-image extents.
    return row['screen_context'] and row['window_scale']>1 and row['selected_class']=='NSBitmapImageRep' and (
        row['selected_width']<math.floor(row['destination_width']*row['window_scale']+.5)
        or row['selected_height']<math.floor(row['destination_height']*row['window_scale']+.5))


def summarize(directory):
    resources={};anonymous=[];errors=[];processes={}
    for path in sorted(directory.glob('*.jsonl')):
        for line in path.read_text().splitlines():
            row=json.loads(line)
            if 'trace_error' in row:
                errors.append(dict(log=str(path),**row));continue
            processes[row['pid']]=row['executable']
            name=row['resource']
            if not name:
                anonymous.append(row);continue
            source=Path(name);canonical=str(source.resolve())
            item=resources.setdefault(canonical,dict(paths=set(),executables=set(),names=set(),draws=[],sha256=None))
            item['paths'].add(name);item['executables'].add(row['executable']);item['names'].add(row['name'])
            if source.is_file() and item['sha256'] is None:item['sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
            item['draws'].append(dict({key:row[key] for key in ['window','window_title','window_scale','screen_context',
                'logical_width','logical_height','destination_width','destination_height','selected_class',
                'selected_width','selected_height','representations']},
                pattern_selection=row.get('pattern_selection',False)))
    for item in resources.values():
        for key in ['paths','executables','names']:item[key]=sorted(item[key])
        item['potential_undersampled_draws']=[row for row in item['draws'] if undersampled(row)]
    return dict(resources=resources,processes=processes,anonymous_draws=anonymous,errors=errors,
        potential_undersampled_anonymous_draws=[row for row in anonymous if undersampled(row)],
        resource_groups=len(resources),draw_records=sum(len(item['draws']) for item in resources.values())+len(anonymous),
        native_pixel_extent_rounding='nearest',
        nsimage_draw_api_only=not any(d.get('pattern_selection',False) for i in resources.values() for d in i['draws'])
            and not any(d.get('pattern_selection',False) for d in anonymous),
        pattern_selection_records=sum(d.get('pattern_selection',False) for i in resources.values() for d in i['draws'])
            +sum(d.get('pattern_selection',False) for d in anonymous),direct_bitmap_and_cursor_coverage_complete=False,
        consumer_usage_observed=True,design_fidelity_qualified=False,full_plan_complete=False)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--traces',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();result=summarize(args.traces)
    args.output.write_text(json.dumps(result,indent=2)+'\n');assert not result['errors'],result['errors']
    print(f"Observed {result['draw_records']} draws of {result['resource_groups']} file-backed images.")
    print('Resolution candidates:')
    for name,item in result['resources'].items():
        if item['potential_undersampled_draws']:print(name)
    print('Anonymous resolution candidates:',len(result['potential_undersampled_anonymous_draws']))
