# -*- coding: utf-8 -*-
"""KNN time series classification.

This class is a KNN classifier which supports time series distance measures.
The class has hardcoded string references to numba based distances in sktime.distances.
It can also be used with callables, or sktime (pairwise transformer) estimators.

This is a direct wrap or sklearn KNeighbors, with added functionality that allows
time series distances to be passed, and the sktime time series classifier interface.

todo: add a utility method to set keyword args for distance measure parameters.
(e.g.  handle the parameter name(s) that are passed as metric_params automatically,
depending on what distance measure is used in the classifier (e.g. know that it is w
for dtw, c for msm, etc.). Also allow long-format specification for
non-standard/user-defined measures e.g. set_distance_params(measure_type=None,
param_values_to_set=None,
param_names=None)
"""

__author__ = ["jasonlines", "TonyBagnall", "chrisholder", "fkiraly"]
__all__ = ["KNeighborsTimeSeriesClassifier"]

from sklearn.neighbors import KNeighborsClassifier
from sklearn.neighbors._base import _check_weights

from sktime.classification.base import BaseClassifier
from sktime.distances import pairwise_distance

# add new distance string codes here
DISTANCES_SUPPORTED = [
    "euclidean",
    # Euclidean will default to the base class distance
    "dtw",
    "ddtw",
    "wdtw",
    "wddtw",
    "lcss",
    "edr",
    "erp",
    "msm",
]


class KNeighborsTimeSeriesClassifier(BaseClassifier):
    """KNN Time Series Classifier.

    An adapted version of the scikit-learn KNeighborsClassifier for time series data.

    This class is a KNN classifier which supports time series distance measures.
    It has hardcoded string references to numba based distances in sktime.distances,
    and can also be used with callables, or sktime (pairwise transformer) estimators.

    Parameters
    ----------
    n_neighbors : int, set k for knn (default =1)
    weights : {'uniform', 'distance'} or callable, default='uniform'
        Weight function used in prediction.  Possible values:
        - 'uniform' : uniform weights.  All points in each neighborhood
          are weighted equally.
        - 'distance' : weight points by the inverse of their distance.
          in this case, closer neighbors of a query point will have a
          greater influence than neighbors which are further away.
        - [callable] : a user-defined function which accepts an
          array of distances, and returns an array of the same shape
          containing the weights.
    algorithm : str, optional. default = 'brute'
        search method for neighbours
        one of {'auto’, 'ball_tree', 'kd_tree', 'brute'}
    distance : str or callable, optional. default ='dtw'
        distance measure between time series
        if str, must be one of the following strings:
            'euclidean', 'squared', 'dtw', 'ddtw', 'wdtw', 'wddtw',
            'lcss', 'edr', 'erp', 'msm'
        this will substitute a hard-coded distance metric from sktime.distances
        When mpdist is used, the subsequence length (parameter m) must be set
            Example: knn_mpdist = KNeighborsTimeSeriesClassifier(
                                metric='mpdist', metric_params={'m':30})
        if callable, must be of signature (X: Panel, X2: Panel) -> np.ndarray
            output must be mxn array if X is Panel of m Series, X2 of n Series
            if distance_mtype is not set, must be able to take
                X, X2 which are pd_multiindex and numpy3D mtype
        can be pairwise panel transformer inheriting from BasePairwiseTransformerPanel
    distance_params : dict, optional. default = None.
        dictionary for metric parameters , in case that distane is a str
    distance_mtype : str, or list of str optional. default = None.
        mtype that distance expects for X and X2, if a callable
            only set this if distance is not BasePairwiseTransformerPanel descendant
    leaf_size : int, default=30
        Leaf size passed to BallTree or KDTree.  This can affect the
        speed of the construction and query, as well as the memory
        required to store the tree.  The optimal value depends on the
        nature of the problem.
    n_jobs : int, default=None
        The number of parallel jobs to run for neighbors search.
        ``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
        ``-1`` means using all processors. See :term:`Glossary <n_jobs>`
        for more details.
        Doesn't affect :meth:`fit` method.

    Examples
    --------
    >>> from sktime.classification.distance_based import KNeighborsTimeSeriesClassifier
    >>> from sktime.datasets import load_unit_test
    >>> X_train, y_train = load_unit_test(return_X_y=True, split="train")
    >>> X_test, y_test = load_unit_test(return_X_y=True, split="test")
    >>> classifier = KNeighborsTimeSeriesClassifier(distance="euclidean")
    >>> classifier.fit(X_train, y_train)
    KNeighborsTimeSeriesClassifier(...)
    >>> y_pred = classifier.predict(X_test)
    """

    _tags = {
        "capability:multivariate": True,
        "X_inner_mtype": ["pd-multiindex", "numpy3D"],
        "classifier_type": "distance",
    }

    def __init__(
        self,
        n_neighbors=1,
        weights="uniform",
        algorithm="brute",
        distance="dtw",
        distance_params=None,
        distance_mtype=None,
        leaf_size=30,
        n_jobs=None,
    ):
        self.n_neighbors = n_neighbors
        self.weights = _check_weights(weights)
        self.algorithm = algorithm
        self.distance = distance
        self.distance_params = distance_params
        self.distance_mtype = distance_mtype
        self.leaf_size = leaf_size
        self.n_jobs = n_jobs

        # translate distance strings into distance callables
        if isinstance(distance, str) and distance not in DISTANCES_SUPPORTED:
            raise ValueError(
                f"Unrecognised distance measure string: {distance}. "
                f"Allowed values for string codes are: {DISTANCES_SUPPORTED}. "
                "Alternatively, pass a callable distance measure into the constuctor."
            )

        self.knn_estimator_ = KNeighborsClassifier(
            n_neighbors=n_neighbors,
            algorithm=algorithm,
            metric="precomputed",
            metric_params=distance_params,
            leaf_size=leaf_size,
            n_jobs=n_jobs,
            weights=weights,
        )

        super(KNeighborsTimeSeriesClassifier, self).__init__()

        # the distances in sktime.distances want numpy3D
        #   otherwise all Panel formats are ok
        if isinstance(self.distance, str):
            self.set_tags(X_inner_mtype="numpy3D")
        elif distance_mtype is not None:
            self.set_tags(X_inner_mtype=distance_mtype)

    def _distance(self, X, X2):
        """Compute distance - unified interface to str code and callable."""
        distance = self.distance
        distance_params = self.distance_params
        if distance_params is None:
            distance_params = {}

        if isinstance(distance, str):
            return pairwise_distance(X, X2, distance, **distance_params)
        else:
            return distance(X, X2)

    def _fit(self, X, y):
        """Fit the model using X as training data and y as target values.

        Input number of cases (n), with series of dimension (d), each series length (d).

        Parameters
        ----------
        X : sktime-format pandas dataframe with shape(n,d),
            or numpy ndarray with shape(n,d,m)

        y : {array-like, sparse matrix}
            Target values of shape = [n]
        """
        # store full data as indexed X
        self._X = X

        dist_mat = self._distance(X, X)

        self.knn_estimator_.fit(dist_mat, y)

        return self

    def kneighbors(self, X, n_neighbors=None, return_distance=True):
        """Find the K-neighbors of a point.

        Returns indices of and distances to the neighbors of each point.

        Parameters
        ----------
        X : sktime-compatible data format, Panel or Series, with n_samples series
        y : {array-like, sparse matrix}
            Target values of shape = [n_samples]
        n_neighbors : int
            Number of neighbors to get (default is the value
            passed to the constructor).
        return_distance : boolean, optional. Defaults to True.
            If False, distances will not be returned

        Returns
        -------
        dist : array
            Array representing the lengths to points, only present if
            return_distance=True
        ind : array
            Indices of the nearest points in the population matrix.
        """
        self.check_is_fitted()

        # self._X should be the stored _X
        dist_mat = self._distance(X, self._X)

        neigh_ind = self.knn_estimator_.kneighbors(
            dist_mat, n_neighbors=n_neighbors, return_distance=return_distance
        )

        return neigh_ind

    def _predict(self, X):
        """Predict the class labels for the provided data.

        Parameters
        ----------
        X : sktime-compatible Panel data format, with n_samples series

        Returns
        -------
        y : array of shape [n_samples] or [n_samples, n_outputs]
            Class labels for each data sample.
        """
        # self._X should be the stored _X
        dist_mat = self._distance(X, self._X)

        y_pred = self.knn_estimator_.predict(dist_mat)

        return y_pred

    def _predict_proba(self, X):
        """Return probability estimates for the test data X.

        Parameters
        ----------
        X : sktime-compatible Panel data format, with n_samples series

        Returns
        -------
        p : array of shape = [n_samples, n_classes], or a list of n_outputs
            of such arrays if n_outputs > 1.
            The class probabilities of the input samples. Classes are ordered
            by lexicographic order.
        """
        # self._X should be the stored _X
        dist_mat = self._distance(X, self._X)

        y_pred = self.knn_estimator_.predict_proba(dist_mat)

        return y_pred
