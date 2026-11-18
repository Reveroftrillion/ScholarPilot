"""Independent numerical checks for illustrative examples, not model scores."""
import math

def main():
    prior, sensitivity, false_positive = .01, .9, .05
    posterior = prior*sensitivity/(prior*sensitivity+(1-prior)*false_positive)
    assert math.isclose(posterior, .15384615384615385)
    w, x, target, rate = 2., 3., 5., .1
    gradient = (w*x-target)*x
    updated = w-rate*gradient
    assert math.isclose(updated,1.7)
    assert .5*(updated*x-target)**2 < .5*(w*x-target)**2
    weights=[math.exp(x) for x in (0.,1.)]
    weights=[x/sum(weights) for x in weights]
    assert math.isclose(sum(weights),1.) and all(x>=0 for x in weights)
    print('Bayes posterior, gradient update, softmax normalization: 3/3')
if __name__=='__main__':main()
