from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from scipy.linalg import block_diag

from library_prep_plate_prep import costs

pd.set_option('future.no_silent_downcasting', True)

__all__ = ['SequencingSamples', 'Plate', 'Plate_96W', 'Plates']


class Geometry(ABC):
    def __init__(self, cost_matrix=None):
        self._cost_matrix = cost_matrix

    @property
    def cost_matrix(self):
        return self.cost_fn.all_pairs(self.x, self.y)


class PointCloud(Geometry):
    def __init__(self, x, y=None, cost_fn=None, **kwargs):
        super().__init__(**kwargs)
        self.x = x
        self.y = self.x if y is None else y

        self.cost_fn = costs.SameFamily() if cost_fn is None else cost_fn


class SequencingSamples(PointCloud):
    def __init__(self, data: pd.DataFrame, cost_fn=None, **kwargs):
        super().__init__(np.arange(data.shape[0]), cost_fn, **kwargs)
        self._data = data
        self.design = self._pp(data)

    @classmethod
    def from_samples(cls, df, n_empty, n_controls, cost_fn=None):
        """When input data is missing controls, blanks."""
        nonsample_idx = pd.Index(['empty'] * n_empty + ['control'] * n_controls)

        # NOTE: Use na sentinel -1
        nonsample_df = df.head(nonsample_idx.size).mul(0).add(-1)
        nonsample_df.index = nonsample_idx
        data = pd.concat([df, nonsample_df])

        return cls(data, cost_fn)

    @property
    def cost_matrix(self):
        """Re-define for sample covariate geometries."""
        return self.cost_fn.all_pairs(self.design)

    def _pp(self, data):
        """Check and preprocess data."""
        def _enc_cat(s):
            codes, _ = pd.factorize(s, use_na_sentinel=True)
            return codes

        data_ = data.copy(deep=True)

        for var in ['donor', 'timepoint', 'family']:
            data_[var] = _enc_cat(data_[var])

        return data_.values


class Grid(Geometry):
    def __init__(self, x, cost_fn=None, **kwargs):
        super().__init__(**kwargs)
        self.x = x
        self.grid_size = tuple(xs.shape[0] for xs in x)
        self.num_a = np.array(self.grid_size).prod()
        self.grid_dimension = len(self.x)

        self.cost_fn = costs.SqEuclidean() if cost_fn is None else cost_fn

    @property
    def cost_matrix(self):
        return self.cost_fn.all_pairs(self.x)


class Plate(Grid):
    def __init__(self, columns, rows, cost_fn=None, **kwargs):
        self.columns = columns
        self.rows = rows
        self.x_y = np.array(list(np.ndindex(columns, rows))) + 1

        # super().__init__(self._rc2x(), cost_fn, **kwargs)
        super().__init__(self.x_y, cost_fn, **kwargs)
        self.wells = self.num_a

    def _rc2x(self):
        return [(np.arange(getattr(self, n)) + 1) for n in ['columns', 'rows']]


class Plate_96W(Plate):
    def __init__(self, cost_fn=None, **kwargs):
        super().__init__(12, 8, cost_fn, **kwargs)


class Plates(Geometry):
    def __init__(self, columns: list[int], rows: list[int], cost_fn=None, **kwargs):
        self._plates = [Plate(c, r, cost_fn=cost_fn, **kwargs) for c, r in zip(columns, rows)]

    @property
    def cost_matrix(self):
        """Re-define for lists of plate geometries."""
        return block_diag(*[_plate.cost_matrix for _plate in self._plates])

    @property
    def p_x_y(self):
        def pidx(a, c):
            return np.pad(a, ((0,0), (1,0)), constant_values=c)
        return np.concatenate([pidx(p.x_y, i) for i, p in enumerate(self._plates)])