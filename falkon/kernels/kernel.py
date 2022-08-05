# -*- coding: utf-8 -*-
import dataclasses
import warnings
from abc import ABC, abstractmethod
from typing import Optional

from falkon.mmv_ops.fmm_cpu import fmm_cpu_sparse, fmm_cpu
from falkon.mmv_ops.fmmv_cpu import fdmmv_cpu_sparse, fmmv_cpu_sparse, fmmv_cpu, fdmmv_cpu
from falkon.utils.helpers import check_same_dtype, check_sparse, check_same_device
from falkon.utils import decide_cuda
from falkon.options import FalkonOptions


class Kernel(ABC):
    def __init__(self, name, kernel_type, opt: Optional[FalkonOptions]):
        self.name = name
        self.kernel_type = kernel_type
        if opt is None:
            opt = FalkonOptions()
        self.params: FalkonOptions = opt

    @staticmethod
    def _check_dmmv_dimensions(X1, X2, v, w, out):
        # Parameter validation
        if v is None and w is None:
            raise ValueError("One of v and w must be specified to run fdMMV.")

        if X1.dim() != 2:
            raise ValueError("Matrix X1 must be 2D.")
        if X2.dim() != 2:
            raise ValueError("Matrix X2 must be 2D.")
        if v is not None and v.dim() == 1:
            v = v.reshape((-1, 1))
        if v is not None and v.dim() != 2:
            raise ValueError(
                f"v must be a vector or a 2D matrix. Found {len(v.shape)}D.")
        if w is not None and w.dim() == 1:
            w = w.reshape((-1, 1))
        if w is not None and w.dim() != 2:
            raise ValueError(
                f"w must be a vector or a 2D matrix. Found {len(w.shape)}D.")

        T = v.size(1) if v is not None else w.size(1)
        M = X2.size(0)
        if out is not None and out.shape != (M, T):
            raise ValueError(
                f"Output dimension is incorrect. "
                f"Expected ({M}, {T}) found {out.shape}")
        if v is not None and v.shape != (X2.size(0), T):
            raise ValueError(
                f"Dimensions of matrix v are incorrect: "
                f"Expected ({M}, {T}) found {v.shape}")
        if w is not None and w.shape != (X1.size(0), T):
            raise ValueError(
                f"Dimensions of matrix w are incorrect: "
                f"Expected ({X1.size(0)}, {T}) found {w.shape}")

        if not check_same_dtype(X1, X2, v, w, out):
            raise TypeError("Data types of input matrices must be equal.")

        return X1, X2, v, w, out

    @staticmethod
    def _check_mmv_dimensions(X1, X2, v, out):
        # Parameter validation
        if X1.dim() != 2:
            raise ValueError("Matrix X1 must be 2D.")
        if X2.dim() != 2:
            raise ValueError("Matrix X2 must be 2D.")
        if v.dim() == 1:
            v = v.reshape((-1, 1))
        if v.dim() != 2:
            raise ValueError(
                f"v must be a vector or a 2D matrix. Found {len(v.shape)}D.")

        if out is not None and out.shape != (X1.size(0), v.size(1)):
            raise ValueError(
                f"Output dimension is incorrect. "
                f"Expected ({X1.size(0)}, {v.size(1)}) found {out.shape}")
        if v.shape != (X2.size(0), v.size(1)):
            raise ValueError(
                f"Dimensions of matrix v are incorrect: "
                f"Expected ({X2.size(0)}, {v.size(1)}) found {v.shape}")

        if not check_same_dtype(X1, X2, v, out):
            raise TypeError("Data types of input matrices must be equal.")

        return X1, X2, v, out

    @staticmethod
    def _check_mm_dimensions(X1, X2, out):
        # Parameter validation
        if X1.dim() != 2:
            raise ValueError("Matrix X1 must be 2D.")
        if X2.dim() != 2:
            raise ValueError("Matrix X2 must be 2D.")
        N = X1.size(0)
        M = X2.size(0)
        if out is not None and out.shape != (N, M):
            raise ValueError(
                f"Output dimension is incorrect. "
                f"Expected ({N}, {M}) found {out.shape}")

        if not check_same_dtype(X1, X2, out):
            raise TypeError("Data types of input matrices must be equal.")

        return X1, X2, out

    @staticmethod
    def _check_device_properties(*args, fn_name: str, opt: FalkonOptions):
        if not check_same_device(*args):
            raise RuntimeError("All input arguments to %s must be on the same device" % (fn_name))

    def __call__(self, X1, X2, out=None, opt: Optional[FalkonOptions] = None):
        X1, X2, out = self._check_mm_dimensions(X1, X2, out)
        self._check_device_properties(X1, X2, out, fn_name="kernel", opt=opt)
        params = self.params
        if opt is not None:
            params = dataclasses.replace(self.params, **dataclasses.asdict(opt))
        mm_impl = self._decide_mm_impl(X1, X2, params)
        return mm_impl(X1, X2, self, out, params)

    def _decide_mm_impl(self, X1, X2, opt: FalkonOptions):
        use_cuda = decide_cuda(opt)
        sparsity = check_sparse(X1, X2)
        if not all(sparsity) and any(sparsity):
            raise ValueError("Either all or none of 'X1', 'X2' must be sparse.")
        sparsity = all(sparsity)
        if (X1.device.type == 'cuda') and (not use_cuda):
            warnings.warn("kernel backend was chosen to be CPU, but GPU input tensors found. "
                          "Defaulting to use the GPU (note this may cause issues later). "
                          "To force usage of the CPU backend, please pass CPU tensors; "
                          "to avoid this warning if the GPU backend is "
                          "desired, check your options (i.e. set 'use_cpu=False').")
            use_cuda = True
        if use_cuda:
            from falkon.mmv_ops.fmm_cuda import fmm_cuda, fmm_cuda_sparse
            if sparsity:
                return fmm_cuda_sparse
            else:
                return fmm_cuda
        else:
            if sparsity:
                return fmm_cpu_sparse
            else:
                return fmm_cpu

    # Kernel(X1, X2)*v
    def mmv(self, X1, X2, v, out=None, opt: Optional[FalkonOptions] = None):
        X1, X2, v, out = self._check_mmv_dimensions(X1, X2, v, out)
        self._check_device_properties(X1, X2, v, out, fn_name="mmv", opt=opt)

        params = self.params
        if opt is not None:
            params = dataclasses.replace(self.params, **dataclasses.asdict(opt))
        mmv_impl = self._decide_mmv_impl(X1, X2, v, params)
        return mmv_impl(X1, X2, v, self, out, params)

    def _decide_mmv_impl(self, X1, X2, v, opt: FalkonOptions):
        use_cuda = decide_cuda(opt)
        sparsity = check_sparse(X1, X2)
        if not all(sparsity) and any(sparsity):
            raise ValueError("Either all or none of 'X1', 'X2' must be sparse.")
        if (X1.device.type == 'cuda') and (not use_cuda):
            warnings.warn("kernel-vector product backend was chosen to be CPU, but GPU input "
                          "tensors found. Defaulting to use the GPU (note this may "
                          "cause issues later). To force usage of the CPU backend, "
                          "please pass CPU tensors; to avoid this warning if the GPU backend is "
                          "desired, check your options (i.e. set 'use_cpu=False').")
            use_cuda = True
        sparsity = all(sparsity)
        if use_cuda:
            from falkon.mmv_ops.fmmv_cuda import fmmv_cuda, fmmv_cuda_sparse
            if sparsity:
                return fmmv_cuda_sparse
            else:
                return fmmv_cuda
        else:
            if sparsity:
                return fmmv_cpu_sparse
            else:
                return fmmv_cpu

    # Kernel(X1, X2)'*(Kernel(X1, X2)*v + w)
    def dmmv(self, X1, X2, v, w, out=None, opt: Optional[FalkonOptions] = None):
        X1, X2, v, w, out = self._check_dmmv_dimensions(X1, X2, v, w, out)
        self._check_device_properties(X1, X2, v, w, out, fn_name="dmmv", opt=opt)
        params = self.params
        if opt is not None:
            params = dataclasses.replace(self.params, **dataclasses.asdict(opt))
        dmmv_impl = self._decide_dmmv_impl(X1, X2, v, w, params)
        return dmmv_impl(X1, X2, v, w, self, out, params)

    def _decide_dmmv_impl(self, X1, X2, v, w, opt: FalkonOptions):
        use_cuda = decide_cuda(opt)
        sparsity = check_sparse(X1, X2)
        if not all(sparsity) and any(sparsity):
            raise ValueError("Either all or none of 'X1', 'X2' must be sparse.")
        if (X1.device.type == 'cuda') and (not use_cuda):
            warnings.warn("kernel-vector double product backend was chosen to be CPU, but GPU "
                          "input tensors found. Defaulting to use the GPU (note this may "
                          "cause issues later). To force usage of the CPU backend, "
                          "please pass CPU tensors; to avoid this warning if the GPU backend is "
                          "desired, check your options (i.e. set 'use_cpu=False').")
            use_cuda = True
        sparsity = all(sparsity)
        if use_cuda:
            from falkon.mmv_ops.fmmv_cuda import fdmmv_cuda, fdmmv_cuda_sparse
            if sparsity:
                return fdmmv_cuda_sparse
            else:
                return fdmmv_cuda
        else:
            if sparsity:
                return fdmmv_cpu_sparse
            else:
                return fdmmv_cpu

    @abstractmethod
    def _prepare(self, X1, X2):
        pass

    @abstractmethod
    def _apply(self, X1, X2, out):
        pass

    @abstractmethod
    def _finalize(self, A, d):
        pass

    @abstractmethod
    def _prepare_sparse(self, X1, X2):
        raise NotImplementedError("_prepare_sparse not implemented for kernel %s" %
                                  (self.kernel_type))

    @abstractmethod
    def _apply_sparse(self, X1, X2, out):
        raise NotImplementedError("_apply_sparse not implemented for kernel %s" %
                                  (self.kernel_type))

    def __str__(self):
        return f"<{self.name} kernel>"
