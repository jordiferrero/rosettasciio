# -*- coding: utf-8 -*-
# Copyright 2007-2022 The HyperSpy developers
#
# This file is part of RosettaSciIO.
#
# RosettaSciIO is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# RosettaSciIO is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with RosettaSciIO. If not, see <https://www.gnu.org/licenses/#GPL>.

from packaging.version import Version
import mrcz as _mrcz
import logging
from rsciio.utils.tools import DTBox


_logger = logging.getLogger(__name__)


_POP_FROM_HEADER = [
    "compressor",
    "MRCtype",
    "C3",
    "dimensions",
    "dtype",
    "extendedBytes",
    "gain",
    "maxImage",
    "minImage",
    "meanImage",
    "metaId",
    "packedBytes",
    "pixelsize",
    "pixelunits",
    "voltage",
]
# Hyperspy uses an unusual mixed Fortran- and C-ordering scheme
_READ_ORDER = [1, 2, 0]
_WRITE_ORDER = [0, 1, 2]


# API changes in mrcz 0.5
def _parse_metadata(metadata):
    if Version(_mrcz.__version__) < Version("0.5"):
        return metadata[0]
    else:
        return metadata


mapping = {
    "mrcz_header.voltage": ("Acquisition_instrument.TEM.beam_energy", _parse_metadata),
    "mrcz_header.gain": (
        "Signal.Noise_properties.Variance_linear_model.gain_factor",
        _parse_metadata,
    ),
    # There is no metadata field for spherical aberration
    #'mrcz_header.C3':
    # ("Acquisition_instrument.TEM.C3", lambda x: x),
}


def file_reader(filename, endianess="<", lazy=False, mmap_mode="c", **kwds):
    _logger.debug("Reading MRCZ file: %s" % filename)

    if mmap_mode != "c":
        # Note also that MRCZ does not support memory-mapping of compressed data.
        # Perhaps we could use the zarr package for that
        raise ValueError("MRCZ supports only C-ordering memory-maps")

    mrcz_endian = "le" if endianess == "<" else "be"
    data, mrcz_header = _mrcz.readMRC(
        filename, endian=mrcz_endian, useMemmap=lazy, pixelunits="nm", **kwds
    )

    # Create the axis objects for each axis
    names = ["y", "x", "z"]
    navigate = [False, False, True]
    axes = [
        {
            "size": data.shape[hsIndex],
            "index_in_array": hsIndex,
            "name": names[index],
            "scale": mrcz_header["pixelsize"][hsIndex],
            "offset": 0.0,
            "units": mrcz_header["pixelunits"],
            "navigate": nav,
        }
        for index, (hsIndex, nav) in enumerate(zip(_READ_ORDER, navigate))
    ]
    axes.insert(0, axes.pop(2))  # re-order the axes

    metadata = mrcz_header.copy()
    # Remove non-standard fields
    for popTarget in _POP_FROM_HEADER:
        metadata.pop(popTarget)

    dictionary = {
        "data": data,
        "axes": axes,
        "metadata": metadata,
        "original_metadata": {"mrcz_header": mrcz_header},
        "mapping": mapping,
    }

    return [
        dictionary,
    ]


def file_writer(
    filename, signal, do_async=False, compressor=None, clevel=1, n_threads=None, **kwds
):
    endianess = kwds.pop("endianess", "<")
    mrcz_endian = "le" if endianess == "<" else "be"

    md = DTBox(signal["metadata"], box_dots=True)

    # Get pixelsize and pixelunits from the axes
    pixelunits = signal["axes"][-1]["units"]
    pixelsize = [signal["axes"][I]["scale"] for I in _WRITE_ORDER]

    # Strip out voltage from meta-data
    voltage = md.get("Acquisition_instrument.TEM.beam_energy")
    # There aren't hyperspy fields for spherical aberration or detector gain
    C3 = 0.0
    gain = md.get("Signal.Noise_properties.Variance_linear_model.gain_factor", 1.0)
    if do_async:
        _mrcz.asyncWriteMRC(
            signal["data"],
            filename,
            meta=md,
            endian=mrcz_endian,
            pixelsize=pixelsize,
            pixelunits=pixelunits,
            voltage=voltage,
            C3=C3,
            gain=gain,
            compressor=compressor,
            clevel=clevel,
            n_threads=n_threads,
        )
    else:
        _mrcz.writeMRC(
            signal["data"],
            filename,
            meta=md,
            endian=mrcz_endian,
            pixelsize=pixelsize,
            pixelunits=pixelunits,
            voltage=voltage,
            C3=C3,
            gain=gain,
            compressor=compressor,
            clevel=clevel,
            n_threads=n_threads,
        )
