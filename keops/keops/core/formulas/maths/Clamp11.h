#pragma once

#include "core/utils/keops_math.h"
#include "core/autodiff/VectorizedScalarUnaryOp.h"
#include "core/formulas/maths/Sin.h"
#include "core/formulas/maths/Minus.h"
#include "core/formulas/maths/Mult.h"
#include "core/formulas/maths/Inv.h"
#include "core/formulas/maths/Sqrt.h"
#include "core/formulas/maths/Subtract.h"
#include "core/formulas/constants/IntConst.h"
#include "core/formulas/maths/Square.h"


namespace keops {

//////////////////////////////////////////////////////////////
////               CLAMP11 :  Clamp11< F >                ////
//////////////////////////////////////////////////////////////



template<class F>
struct Clamp11 : VectorizedScalarUnaryOp<Clamp11, F> {

  static void PrintIdString(::std::stringstream &str) { str << "Clamp11"; }

  template < typename TYPE >
  struct Operation_Scalar {
    DEVICE INLINE void operator() (TYPE &out, TYPE &outF) {
          out = keops_clamp11(outF);
    }
  };

  template<class V, class GRADIN>
  using DiffT = typename F::template DiffT<V, Mult<F, GRADIN>>;

};

#define Clamp11(f) KeopsNS<Clamp11<decltype(InvKeopsNS(f))>>()

}
