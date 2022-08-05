from typing import Optional, List, Union

import torch
from falkon.options import FalkonOptions, KeopsOptions
from falkon.utils.switches import decide_keops
from falkon.sparse import SparseTensor

try:
    from falkon.mmv_ops.keops import run_keops_mmv
    _has_keops = True
except ModuleNotFoundError:
    _has_keops = False

__all__ = ("should_use_keops", "KeopsKernelMixin", )


def should_use_keops(T1: Union[torch.Tensor, SparseTensor],
                     T2: Union[torch.Tensor, SparseTensor],
                     opt: KeopsOptions) -> bool:
    """Check whether the conditions to use KeOps for mmv operations are satisfied

    Parameters
    ----------
    T1 : tensor
        The first 2D tensor in the MMV operation
    T2 : tensor
        The second 2D tensor in the MMV operation
    opt : KeopsOptions
        Options governing KeOps usage. Significant option is `keops_active`.

    Returns
    -------
    Whether KeOps will be used for MMV operations. The decision is based on the options, and
    on the inputs. In particular, if inputs are sparse or high-dimensional, KeOps does not work
    (or is too slow) and this function returns `False`. Further, if KeOps is not installed
    then this function will return `False`.
    """
    # No handling of sparse tensors
    if not isinstance(T1, torch.Tensor) or not isinstance(T2, torch.Tensor) \
            or T1.is_sparse or T2.is_sparse:
        return False
    # No handling if keops is not installed correctly or 'keops_active' is 'no'
    if not decide_keops(opt):
        return False
    # No handling for high dimensional data (https://github.com/getkeops/keops/issues/57)
    # unless keops_active is in 'force' mode.
    if T1.shape[1] > 50 and not opt.keops_active == "force":
        return False

    return True


# noinspection PyMethodMayBeStatic
class KeopsKernelMixin():
    def keops_mmv(self,
                  X1: torch.Tensor,
                  X2: torch.Tensor,
                  v: torch.Tensor,
                  out: Optional[torch.Tensor],
                  formula: str,
                  aliases: List[str],
                  other_vars: List[torch.Tensor],
                  opt: FalkonOptions):
        if not _has_keops:
            raise ModuleNotFoundError("Module 'pykeops' is not properly installed. "
                                      "Please install 'pykeops' before running 'keops_mmv'.")
        if other_vars is None:
            other_vars = []
        return run_keops_mmv(X1=X1, X2=X2, v=v, other_vars=other_vars,
                             out=out, formula=formula, aliases=aliases, axis=1,
                             reduction='Sum', opt=opt)

    def keops_dmmv_helper(self, X1, X2, v, w, kernel, out, opt, mmv_fn):
        """
        performs fnc(X1*X2', X1, X2)' * ( fnc(X1*X2', X1, X2) * v  +  w )

        Parameters
        -----------
        X1 : Tensor N x D
        X2 : Tensor M x D
        v  : Tensor M x T
        w  : Tensor N x T
        kernel : falkon.Kernel
        out : Tensor M x T or None
        opt : FalkonOptions
        mmv_fn : Callable

        Notes
        ------
        The double MMV is implemented as two separate calls to the user-supplied
        `mmv_fn`. The first one calculates the inner part of the formula (NxT)
        while the second calculates the outer matrix-vector multiplication which

        """
        if v is not None and w is not None:
            out1 = mmv_fn(X1, X2, v, kernel, None, opt)
            out1.add_(w)
            return mmv_fn(X2, X1, out1, kernel, out, opt)
        elif v is None:
            return mmv_fn(X2, X1, w, kernel, out, opt)
        elif w is None:
            out1 = mmv_fn(X1, X2, v, kernel, None, opt)
            return mmv_fn(X2, X1, out1, kernel, out, opt)

    # noinspection PyUnusedLocal
    def keops_can_handle_mm(self, X1, X2, opt) -> bool:
        return False

    # noinspection PyUnusedLocal
    def keops_can_handle_mmv(self,
                             X1: Union[torch.Tensor, SparseTensor],
                             X2: Union[torch.Tensor, SparseTensor],
                             v: torch.Tensor,
                             opt: FalkonOptions) -> bool:
        return should_use_keops(X1, X2, opt)

    def keops_can_handle_dmmv(self,
                              X1: Union[torch.Tensor, SparseTensor],
                              X2: Union[torch.Tensor, SparseTensor],
                              v: torch.Tensor,
                              w: torch.Tensor,
                              opt: FalkonOptions) -> bool:
        return (self.keops_can_handle_mmv(X1, X2, v, opt) and
                self.keops_can_handle_mmv(X2, X1, w, opt))
