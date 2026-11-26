import unittest,torch
from trainable import attention,dense

class Trainable(unittest.TestCase):
    def test_gradients(self):
        torch.set_num_threads(1);torch.manual_seed(21)
        for stop in (1,17,63,64):
            inputs=[torch.randn(s,dtype=torch.float64,requires_grad=True) for s in ((3,5),(3,4,5),(3,4,2),(3,4,2))]
            a=attention(*inputs,stop);b=dense(*inputs,stop)
            torch.testing.assert_close(a,b,atol=1e-11,rtol=1e-11)
            ga=torch.autograd.grad(a.square().sum(),inputs);gb=torch.autograd.grad(b.square().sum(),inputs)
            for x,y in zip(ga,gb):torch.testing.assert_close(x,y,atol=1e-11,rtol=1e-11)
if __name__=='__main__':unittest.main()
