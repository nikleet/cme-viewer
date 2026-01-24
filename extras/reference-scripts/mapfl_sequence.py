"""Generate a sequence of launch point files"""

import argparse
import re

import numpy as np
import pyhdf.SD as h4
from predsci.mapfl.mapfl import get_cadence, get_steps, get_hdf_times


def get_labels(fname):
    """retrieves labels from a tracer header file"""
    with open(fname) as label_file:
        label_file.readline() # header
        labels = [label.strip() for label in label_file.readlines()]
    return labels

def get_tracers(hdf_filename):
    """gets tracer data in r, theta, phi"""
    # Open the HDF file
    sd_id = h4.SD(hdf_filename)

    #Read dataset.  In all PSI hdf4 files, the
    #data is stored in "Data-Set-2":
    sds_id = sd_id.select('Data-Set-2')
    f = sds_id.get()
    return f

def get_launch_points(fname):
    """load launch points from lp.dat file
    format is r\tt\tp\tred\tgreen\tblue
    """
    r_posns, theta_posns, phi_posns = [], [], []
    with open(fname, 'r') as bg_file:
        bg_file.readline()
        for line in bg_file.readlines():
            r_pos, theta_pos, phi_pos, _, _, _ = [float(col_) for col_ in line.split('\t')]
            r_posns.append(r_pos)
            theta_posns.append(theta_pos)
            phi_posns.append(phi_pos)
    return np.array(r_posns), np.array(theta_posns), np.array(phi_posns)

def write_labels(labels, fname):
    with open(fname, 'w') as label_file:
        label_file.write('\t'.join(list('rtp')) + '\n')
        for label in labels:
            label_file.write(label + '\n')

def write_launch_points(args):
    times = get_hdf_times('{}/{}'.format(args.cme_directory, args.time_stamps))

    # choose every other lp from 3 - 17
    label_select = args.label_select.split(',')

    for step_name in get_steps(list(times.keys()), args.max_steps):
        time = times[step_name]

        hdf_filename = '{}/{}{}.hdf'.format(args.cme_directory, args.tracer_prefix, step_name)
        try:
            r, theta, phi = get_tracers(hdf_filename)
        except:
            print('could not get tracers from {}'.format(hdf_filename))
            raise

        labels = get_labels('{}/{}'.format(args.cme_directory, args.tracer_header))


        print('number of labels:{}'.format(len(labels)))

        if args.bg_lp is not None:
            r_bg, theta_bg, phi_bg = get_launch_points(args.bg_lp)
            r = np.hstack((r, r_bg))
            theta = np.hstack((theta, theta_bg))
            phi = np.hstack((phi, phi_bg))
            labels.extend(len(phi_bg)*['background'])
            print('after adding background, number of labels:{}'.format(len(labels)))
            # have to do this for forward and reverse?

        # Currently we are trimming the fr labels to combine all the labels to appear as one flux rope
        # TODO: in the future keep the fr labels to organize plotly by fr groups
        trimmed_labels =[]
        max_fr_num = 1
        for label in labels:
            trimmed_labels.append(re.sub(r'fr[0-9]\_', '', label))
            try:
                # the third index of the original label should be the flux rope number
                max_fr_num = max(int(label[2]), max_fr_num)
            except ValueError as e:
                pass


        labels=trimmed_labels

        labels, label_ids, label_orig = np.unique(
            np.array(labels),
            return_index=True,
            return_inverse=True, # access original indices
            )

        print(labels)

        r_group, theta_group, phi_group, label_group = [], [], [], []
        for label_id, label in enumerate(labels):
            group_ids = np.where(label_orig == label_id)[0]
            if label not in ['background']:
                group_ids = group_ids[::get_cadence(group_ids, args.max_traces*max_fr_num)]
            else:
                # THIS IS PURELY FOR EXPLORATION THIS SHOULD BE DONE IN A SMARTER WAY
                group_ids = group_ids[::get_cadence(group_ids, args.max_traces*5)]
            if label in label_select:
                r_group.append(r[group_ids])
                theta_group.append(theta[group_ids])
                phi_group.append(phi[group_ids])
                label_group.append(len(group_ids)*[label])
        r_select = np.hstack(r_group)
        theta_select = np.hstack(theta_group)
        phi_select = np.hstack(phi_group)
        label_select = np.hstack(label_group)

        with open('lp_{}.dat'.format(step_name), 'w') as lp_file:
            lp_file.write('\t'.join(list('rtp')) + '\n')
            for i in range(len(r_select)):
                lp_file.write('{:e}\t{:e}\t{:e}'.format(
                    r_select[i], theta_select[i], phi_select[i]) + '\n')

        write_labels(label_select, 'tracer_header_select.dat')


def main():
    """main entry function"""
    parser = argparse.ArgumentParser(
        description='ps_gen_tracer_pts: generates a selection of launch point files')
    parser.add_argument('--cme_directory',
                        required=True,
                        help='CME directory of magnetic fields and tracer files')
    parser.add_argument('--time_stamps', default='masTimes.txt',
                        help='name of file storing hdf times')
    parser.add_argument('--tracer_header', default='tracer_header.dat',
                        help='name of tracer header file in cme_directory')
    parser.add_argument('--tracer_prefix', default='tracers_pos',
                        help='prefix of input tracer files')
    parser.add_argument('--launch_point_prefix', default='lp_',
                        help='prefix of output launch point files')
    parser.add_argument('--max_traces',
                        type=int,
                        default=20,
                        help='max fieldlines per group (default: %(default)s)')

    parser.add_argument('--label_select',
                        help='list of tracers to select from',
                        default='apex,axis,arcade,ring_lp_04,ring_lp_07,ring_lp_10,ring_lp_13,'+\
                            'ring_lp_16,background')
    parser.add_argument('--bg_lp', default='lp.dat',
                        help="fixed points for background fieldlines (default: %(default)s)")
    parser.add_argument('--verbose', default=False)
    parser.add_argument('--max_steps',
                        default=50,
                        type=int,
                        help="max number of steps to generate (default: %(default)s)")
    args = parser.parse_args()


    write_launch_points(args)

if __name__ == "__main__":
    main()
